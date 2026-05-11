"""
core/storage.py — 云无关存储适配器
=============================================
抽象层：业务代码只调这里，底层可以是 GCS / OSS / 本地文件系统。

平移阿里云只需要：
  1. 实现 AliOSSBackend（把 google-cloud-storage 换成 oss2）
  2. 改环境变量 STORAGE_BACKEND=oss
  3. 业务代码一行不动

当前支持的 backend：
  - local   本地文件系统（开发 / 无云环境兜底）
  - gcs     Google Cloud Storage（当前生产）
  - oss     阿里云 OSS（预留，待平移时实现）

用法：
  from core.storage import get_storage
  store = get_storage()
  store.put(path, data)            # 写文件（bytes）
  store.put_text(path, text)       # 写文本
  store.get(path) -> bytes | None  # 读文件
  store.get_text(path) -> str | None
  store.exists(path) -> bool
  store.delete(path)
  store.list_prefix(prefix) -> list[str]  # 列出前缀下所有路径
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# 抽象接口
# ══════════════════════════════════════════════════════════════════════

class StorageBackend(ABC):
    """所有存储后端实现这个接口，业务代码不直接依赖具体实现。"""

    @abstractmethod
    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        """写入二进制文件。path 是逻辑路径，如 users/uid123/docs/abc.md"""

    @abstractmethod
    def put_text(self, path: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        """写入文本文件。"""

    @abstractmethod
    def get(self, path: str) -> Optional[bytes]:
        """读取二进制文件，不存在返回 None。"""

    @abstractmethod
    def get_text(self, path: str) -> Optional[str]:
        """读取文本文件，不存在返回 None。"""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """路径是否存在。"""

    @abstractmethod
    def delete(self, path: str) -> None:
        """删除文件，不存在时静默忽略。"""

    @abstractmethod
    def list_prefix(self, prefix: str) -> list[str]:
        """列出前缀下所有路径（不含前缀本身），返回相对路径列表。"""


# ══════════════════════════════════════════════════════════════════════
# 本地文件系统（开发 / 兜底）
# ══════════════════════════════════════════════════════════════════════

class LocalStorageBackend(StorageBackend):
    """
    本地文件系统存储。
    根目录由 LOCAL_STORAGE_ROOT 环境变量指定，
    默认为项目根目录下的 .local_storage/
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorage 根目录：%s", self.root)

    def _abs(self, path: str) -> Path:
        # 防止路径穿越
        p = (self.root / path).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"非法路径：{path}")
        return p

    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self._abs(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def put_text(self, path: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        p = self._abs(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def get(self, path: str) -> Optional[bytes]:
        p = self._abs(path)
        if not p.exists():
            return None
        return p.read_bytes()

    def get_text(self, path: str) -> Optional[str]:
        p = self._abs(path)
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def exists(self, path: str) -> bool:
        return self._abs(path).exists()

    def delete(self, path: str) -> None:
        p = self._abs(path)
        if p.exists():
            p.unlink()

    def list_prefix(self, prefix: str) -> list[str]:
        base = self._abs(prefix)
        if not base.exists():
            return []
        results: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                results.append(str(p.relative_to(self.root)))
        return sorted(results)


# ══════════════════════════════════════════════════════════════════════
# Google Cloud Storage
# ══════════════════════════════════════════════════════════════════════

class GCSStorageBackend(StorageBackend):
    """
    GCS 存储后端。
    环境变量：
      GCS_DOC_SPACE_BUCKET  存储桶名称（必填）
      GCP_PROJECT_ID        GCP 项目 ID
    """

    def __init__(self, bucket_name: str, project_id: str = ""):
        try:
            from google.cloud import storage as gcs  # noqa: PLC0415
            self._gcs = gcs
        except ImportError:
            raise RuntimeError("缺少 google-cloud-storage，请运行：pip install google-cloud-storage")

        self._project = project_id
        self._bucket_name = bucket_name
        self._client = None
        self._bucket = None
        logger.info("GCSStorage 初始化：bucket=%s", bucket_name)

    def _get_bucket(self):
        if self._bucket is None:
            self._client = self._gcs.Client(project=self._project or None)
            self._bucket = self._client.bucket(self._bucket_name)
        return self._bucket

    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        blob = self._get_bucket().blob(path)
        blob.upload_from_string(data, content_type=content_type)

    def put_text(self, path: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self.put(path, text.encode("utf-8"), content_type=content_type)

    def get(self, path: str) -> Optional[bytes]:
        try:
            blob = self._get_bucket().blob(path)
            if not blob.exists():
                return None
            return blob.download_as_bytes()
        except Exception as e:
            logger.warning("GCS get 失败 [%s]: %s", path, e)
            return None

    def get_text(self, path: str) -> Optional[str]:
        data = self.get(path)
        if data is None:
            return None
        return data.decode("utf-8")

    def exists(self, path: str) -> bool:
        try:
            return self._get_bucket().blob(path).exists()
        except Exception:
            return False

    def delete(self, path: str) -> None:
        try:
            blob = self._get_bucket().blob(path)
            if blob.exists():
                blob.delete()
        except Exception as e:
            logger.warning("GCS delete 失败 [%s]: %s", path, e)

    def list_prefix(self, prefix: str) -> list[str]:
        try:
            blobs = self._get_bucket().list_blobs(prefix=prefix)
            return sorted(b.name for b in blobs if b.name != prefix)
        except Exception as e:
            logger.warning("GCS list_prefix 失败 [%s]: %s", prefix, e)
            return []


# ══════════════════════════════════════════════════════════════════════
# 阿里云 OSS（预留，平移时实现）
# ══════════════════════════════════════════════════════════════════════

class OSSStorageBackend(StorageBackend):
    """
    阿里云 OSS 存储后端（预留骨架）。
    平移时实现这个类，其余代码零改动。

    环境变量：
      OSS_ENDPOINT        如 oss-cn-hangzhou.aliyuncs.com
      OSS_ACCESS_KEY_ID
      OSS_ACCESS_KEY_SECRET
      OSS_DOC_SPACE_BUCKET  存储桶名称
    """

    def __init__(self, bucket_name: str, endpoint: str, access_key_id: str, access_key_secret: str):
        try:
            import oss2  # noqa: PLC0415
            auth = oss2.Auth(access_key_id, access_key_secret)
            self._bucket = oss2.Bucket(auth, endpoint, bucket_name)
            self._oss2 = oss2
            logger.info("OSSStorage 初始化：bucket=%s endpoint=%s", bucket_name, endpoint)
        except ImportError:
            raise RuntimeError("缺少 oss2，请运行：pip install oss2")

    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        import io  # noqa: PLC0415
        headers = {"Content-Type": content_type}
        self._bucket.put_object(path, io.BytesIO(data), headers=headers)

    def put_text(self, path: str, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
        self.put(path, text.encode("utf-8"), content_type=content_type)

    def get(self, path: str) -> Optional[bytes]:
        try:
            result = self._bucket.get_object(path)
            return result.read()
        except self._oss2.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.warning("OSS get 失败 [%s]: %s", path, e)
            return None

    def get_text(self, path: str) -> Optional[str]:
        data = self.get(path)
        return data.decode("utf-8") if data else None

    def exists(self, path: str) -> bool:
        try:
            return self._bucket.object_exists(path)
        except Exception:
            return False

    def delete(self, path: str) -> None:
        try:
            self._bucket.delete_object(path)
        except Exception as e:
            logger.warning("OSS delete 失败 [%s]: %s", path, e)

    def list_prefix(self, prefix: str) -> list[str]:
        try:
            results = []
            for obj in self._oss2.ObjectIterator(self._bucket, prefix=prefix):
                if obj.key != prefix:
                    results.append(obj.key)
            return sorted(results)
        except Exception as e:
            logger.warning("OSS list_prefix 失败 [%s]: %s", prefix, e)
            return []


# ══════════════════════════════════════════════════════════════════════
# 工厂函数（单例）
# ══════════════════════════════════════════════════════════════════════

_storage_instance: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """
    获取全局存储单例。
    根据环境变量 STORAGE_BACKEND 自动选择：
      local  → LocalStorageBackend（默认）
      gcs    → GCSStorageBackend
      oss    → OSSStorageBackend
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()

    if backend == "gcs":
        bucket = os.getenv("GCS_DOC_SPACE_BUCKET", "").strip()
        if not bucket:
            logger.warning("STORAGE_BACKEND=gcs 但未设置 GCS_DOC_SPACE_BUCKET，降级 local")
            backend = "local"
        else:
            try:
                project = os.getenv("GCP_PROJECT_ID", "").strip()
                _storage_instance = GCSStorageBackend(bucket, project)
                logger.info("存储后端：GCS bucket=%s", bucket)
                return _storage_instance
            except Exception as e:
                logger.warning("GCS 初始化失败，降级 local：%s", e)
                backend = "local"

    if backend == "oss":
        endpoint   = os.getenv("OSS_ENDPOINT", "").strip()
        ak_id      = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
        ak_secret  = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()
        bucket     = os.getenv("OSS_DOC_SPACE_BUCKET", "").strip()
        if not all([endpoint, ak_id, ak_secret, bucket]):
            logger.warning("STORAGE_BACKEND=oss 但 OSS 配置不完整，降级 local")
            backend = "local"
        else:
            try:
                _storage_instance = OSSStorageBackend(bucket, endpoint, ak_id, ak_secret)
                logger.info("存储后端：OSS bucket=%s", bucket)
                return _storage_instance
            except Exception as e:
                logger.warning("OSS 初始化失败，降级 local：%s", e)
                backend = "local"

    # local（默认 / 兜底）
    root_env = os.getenv("LOCAL_STORAGE_ROOT", "").strip()
    if root_env:
        root = Path(root_env)
    else:
        from core.settings import _BASE_DIR  # noqa: PLC0415
        root = _BASE_DIR / ".local_storage"
    _storage_instance = LocalStorageBackend(root)
    logger.info("存储后端：Local root=%s", root)
    return _storage_instance
