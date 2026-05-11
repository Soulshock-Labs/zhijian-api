"""
批量导入礼品卡密（token_type=gift）
用法：
python import_gift_codes.py 小纸笺月度会员_平台标准_100条.csv

说明：
  - 读取 CSV，第 1 列（索引 0）为卡密字符串
  - 写入 redeem_codes.json，token_type 标为 "gift"
  - 已存在的 code 不覆盖（安全）
  - 默认有效期 1 年，服务为月度会员（30天）
  - redeem_codes.json 含真实卡密，已在 .gitignore 中排除；勿提交 Git。部署 Cloud Run 时本地有该文件即可随源码上传。
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 配置 ────────────────────────────────────────────
REDEEM_CODES_FILE = Path(__file__).resolve().parent / "redeem_codes.json"

# 卡密兑换有效期：1 年（用户需在此日期前完成兑换，与兑换后服务时长无关）
EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(days=365)).strftime(
    "%Y-%m-%dT23:59:59+00:00"
)

# 礼品卡对应的服务：兑换后享受 1 个月（30天）月度会员
GIFT_SERVICE = {"type": "membership", "name": "月度会员", "days": 30}
GIFT_DESCRIPTION = "月度会员（礼品）"
GIFT_BATCH = ""  # 从 CSV 第 5 列读取，或留空
# ────────────────────────────────────────────────────


def load_codes(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else []
        return {str(item["code"]).strip().upper(): dict(item) for item in items if isinstance(item, dict) and item.get("code")}
    except Exception as e:
        print(f"[warn] 读取 {path} 失败：{e}，将新建")
        return {}


def save_codes(path: Path, codes: dict[str, dict]) -> None:
    path.write_text(
        json.dumps(list(codes.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_csv(csv_path: Path) -> None:
    codes = load_codes(REDEEM_CODES_FILE)
    added = 0
    skipped = 0

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # 跳过表头
        print(f"[info] 表头：{header}")

        for row in reader:
            if not row:
                continue
            code = str(row[0]).strip().upper()
            if not code:
                continue

            # 从 CSV 读取批次号（第 5 列，索引 4）
            batch = str(row[4]).strip() if len(row) > 4 else ""

            # 从 CSV 读取兑换状态（第 6 列，索引 5）- 如果已标记已用则跳过
            csv_status = str(row[5]).strip().lower() if len(row) > 5 else ""
            if csv_status in ("已使用", "used", "redeemed"):
                print(f"[skip] {code} CSV 已标记已使用")
                skipped += 1
                continue

            if code in codes:
                print(f"[skip] {code} 已存在，不覆盖")
                skipped += 1
                continue

            codes[code] = {
                "code": code,
                "status": "unused",
                "token_type": "gift",
                "expires_at": EXPIRES_AT,
                "service": dict(GIFT_SERVICE),
                "description": GIFT_DESCRIPTION,
                "batch": batch or GIFT_BATCH,
                "source": "csv_import",
            }
            added += 1

    save_codes(REDEEM_CODES_FILE, codes)
    print(f"\n✅ 导入完成：新增 {added} 条，跳过 {skipped} 条，当前库存 {len(codes)} 条")
    print(f"   文件：{REDEEM_CODES_FILE}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python import_gift_codes.py <csv文件路径>")
        print("示例：python import_gift_codes.py 小纸笺月度会员_平台标准_100条.csv")
        sys.exit(1)

    csv_file = Path(sys.argv[1])
    if not csv_file.exists():
        print(f"[错误] 文件不存在：{csv_file}")
        sys.exit(1)

    import_csv(csv_file)
