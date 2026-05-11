from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from core.state import logger
from core.utils import _utc_iso
from services.data_store import _enqueue_webhook_retry, _load_webhook_retries, _save_webhook_retries

async def _fire_webhook_once(url: str, body: dict) -> bool:
    """向第三方发送一次 Webhook POST，返回是否成功（在线程池中执行，不阻塞事件循环）。"""
    import urllib.request
    import urllib.error

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _do_post() -> bool:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SmartTeacher-Webhook/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status < 300
        except Exception as exc:
            logger.warning("Webhook POST 失败 url=%s: %s", url, exc)
            return False

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_post)

async def _dispatch_webhook(callback_url: str, body: dict, order_id: str, code: str) -> None:
    """核销后异步触发 Webhook；失败则写入重试队列。"""
    if not callback_url:
        return
    success = await _fire_webhook_once(callback_url, body)
    if not success:
        retry_item = {
            "id": f"WH-{uuid4().hex[:10]}",
            "callback_url": callback_url,
            "body": body,
            "order_id": order_id,
            "code": code,
            "retry_count": 0,
            "last_attempt_utc": _utc_iso(),
            "status": "pending",
            "created_at_utc": _utc_iso(),
        }
        _enqueue_webhook_retry(retry_item)
        logger.warning("Webhook 首次失败，已加入重试队列 code=%s order=%s", code, order_id)

async def _webhook_retry_loop() -> None:
    """后台定时任务：每 2 分钟重试一次失败的 Webhook，累计 3 次失败后标记 error 并停止重试。"""
    while True:
        await asyncio.sleep(120)
        items = _load_webhook_retries()
        if not items:
            continue
        remaining: list[dict] = []
        for item in items:
            if item.get("status") == "error":
                remaining.append(item)
                continue
            retry_count = int(item.get("retry_count", 0))
            if retry_count >= 3:
                item["status"] = "error"
                logger.error(
                    "Webhook 三次失败已放弃 code=%s order=%s",
                    item.get("code"), item.get("order_id"),
                )
                remaining.append(item)
                continue
            success = await _fire_webhook_once(item.get("callback_url", ""), item.get("body", {}))
            item["retry_count"] = retry_count + 1
            item["last_attempt_utc"] = _utc_iso()
            if success:
                logger.info(
                    "Webhook 重试成功 code=%s order=%s 第%d次",
                    item.get("code"), item.get("order_id"), item["retry_count"],
                )
            else:
                remaining.append(item)
        _save_webhook_retries([i for i in remaining if i.get("status") in ("pending", "error")])
