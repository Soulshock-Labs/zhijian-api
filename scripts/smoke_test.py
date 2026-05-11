#!/usr/bin/env python3
"""
Smoke Test — 重构后轻量验证脚本
覆盖：模块导入 + 核心端点 + NameError 类运行时问题
用法: python3 scripts/smoke_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# Smoke tests must be deterministic and offline. Prevent .env from turning these
# checks into real AI / voice API calls.
os.environ["DASHSCOPE_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["ALLOW_MOCK_CONTENT"] = "0"


def test_module_imports() -> bool:
    """验证所有核心模块可导入（发现循环依赖/缺失依赖）"""
    modules = [
        "core.settings",
        "core.state",
        "core.utils",
        "core.clients",
        "services.data_store",
        "services.redeem_service",
        "services.user_service",
        "services.webhook_service",
        "services.generate_service",
        "services.planning_service",
        "routers.frontend",
        "routers.system",
        "routers.ops",
        "routers.redeem",
        "routers.users",
        "routers.templates",
        "routers.generate",
        "routers.observation",
        "routers.mini",
        "routers.planning",
        "main",
    ]
    ok = True
    print("━" * 50)
    print("模块导入测试")
    print("━" * 50)
    for mod in modules:
        try:
            __import__(mod)
            print(f"  ✓ {mod}")
        except Exception as e:
            ok = False
            print(f"  ✗ {mod}: {type(e).__name__}: {e}")
    return ok


def test_data_store_functions() -> bool:
    """验证 data_store 中的函数运行时不会 NameError"""
    import services.data_store as data_store
    from services.data_store import (
        _load_template_stats,
        _load_app_stats,
        _load_redeem_codes,
    )
    data_store.FIRESTORE_ENABLED = False

    ok = True
    print("\n" + "━" * 50)
    print("Data Store 函数运行时测试")
    print("━" * 50)
    for func in [_load_template_stats, _load_app_stats, _load_redeem_codes]:
        try:
            result = func()
            print(f"  ✓ {func.__name__}() -> {type(result).__name__}")
        except Exception as e:
            ok = False
            print(f"  ✗ {func.__name__}(): {type(e).__name__}: {e}")
    return ok


def test_datetime_helpers() -> bool:
    """验证兑换时间解析不会因缺少时区导致 naive/aware 比较崩溃。"""
    from core.utils import _parse_iso_datetime

    ok = True
    print("\n" + "━" * 50)
    print("时间解析测试")
    print("━" * 50)
    for raw in ("2099-12-31T23:59:59", "2099-12-31T23:59:59+00:00", "2099-12-31T23:59:59Z"):
        dt = _parse_iso_datetime(raw)
        if dt is not None and dt.tzinfo is not None:
            print(f"  ✓ {raw} -> aware datetime")
        else:
            ok = False
            print(f"  ✗ {raw} -> {dt}")
    if _parse_iso_datetime("not-a-date") is None:
        print("  ✓ invalid datetime -> None")
    else:
        ok = False
        print("  ✗ invalid datetime should return None")
    return ok


def test_api_endpoints() -> bool:
    """用 TestClient 验证核心端点"""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    ok = True
    print("\n" + "━" * 50)
    print("API 端点 Smoke 测试")
    print("━" * 50)

    tests = [
        ("GET", "/health", None, 200),
        ("GET", "/public-stats", None, 200),
        ("GET", "/template-standard", None, 200),
        ("GET", "/standard-templates", None, 200),
        ("GET", "/redeem/query?code=VIP2026", None, 200),
        ("GET", "/redeem-codes", None, 200),
    ]

    for method, path, body, expected in tests:
        try:
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=body)
            status = "✓" if resp.status_code == expected else "✗"
            print(f"  {status} {method} {path}: {resp.status_code}")
            if resp.status_code != expected:
                ok = False
        except Exception as e:
            ok = False
            print(f"  ✗ {method} {path}: {type(e).__name__}: {e}")

    # AI 端点（预期 503，因为通常没有配置 DASHSCOPE_API_KEY）
    ai_tests = [
        ("POST", "/preview", {"theme": "test", "phil": "五大领域", "activities": "[]", "class_level": "中班"}, [200, 503]),
        ("POST", "/generate-weekly", {"theme": "test", "phil": "五大领域", "activities": "[]", "class_level": "中班"}, [200, 503]),
    ]
    for method, path, body, expected_list in ai_tests:
        try:
            resp = client.post(path, data=body)
            status = "✓" if resp.status_code in expected_list else "✗"
            print(f"  {status} {method} {path}: {resp.status_code} (AI端点)")
            if resp.status_code not in expected_list:
                ok = False
        except Exception as e:
            ok = False
            print(f"  ✗ {method} {path}: {type(e).__name__}: {e}")

    return ok


def test_webhook_loop() -> bool:
    """验证 webhook 后台任务能启动（不发网络请求）"""
    from services.webhook_service import _webhook_retry_loop
    import asyncio

    print("\n" + "━" * 50)
    print("Webhook 后台任务测试")
    print("━" * 50)

    async def mock_sleep(t: float) -> None:
        raise asyncio.CancelledError("test stop")

    original_sleep = asyncio.sleep
    asyncio.sleep = mock_sleep
    try:
        asyncio.run(_webhook_retry_loop())
    except asyncio.CancelledError:
        print("  ✓ _webhook_retry_loop() 启动正常，sleep 被调用")
        ok = True
    except Exception as e:
        print(f"  ✗ _webhook_retry_loop(): {type(e).__name__}: {e}")
        ok = False
    finally:
        asyncio.sleep = original_sleep
    return ok


def main() -> int:
    print("\n" + "=" * 50)
    print("小纸笺 · Smoke Test")
    print("=" * 50)

    results = [
        test_module_imports(),
        test_data_store_functions(),
        test_datetime_helpers(),
        test_api_endpoints(),
        test_webhook_loop(),
    ]

    print("\n" + "=" * 50)
    if all(results):
        print("🎉 全部通过！")
        print("=" * 50)
        return 0
    else:
        print("⚠️  部分测试失败，请检查上方输出")
        print("=" * 50)
        return 1


if __name__ == "__main__":
    sys.exit(main())
