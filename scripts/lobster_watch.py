#!/usr/bin/env python3
import datetime as dt
import json
import time
from typing import Dict, List, Tuple

import requests


CHECKS: List[Tuple[str, str, str]] = [
    ("home", "https://zhijian.sgsyen.com", "GET"),
    ("health", "https://smart-teacher-api-46126657817.asia-east1.run.app/health", "GET"),
]


def run_check(name: str, url: str, method: str) -> Dict[str, object]:
    started = time.time()
    ok = False
    code = None
    error = ""
    try:
        if method == "GET":
            resp = requests.get(url, timeout=15)
        else:
            resp = requests.post(url, timeout=20)
        code = resp.status_code
        ok = 200 <= code < 300
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    latency_ms = int((time.time() - started) * 1000)
    return {
        "name": name,
        "url": url,
        "method": method,
        "ok": ok,
        "status_code": code,
        "latency_ms": latency_ms,
        "error": error,
    }


def main() -> None:
    timestamp = dt.datetime.utcnow().isoformat() + "Z"
    results = [run_check(name, url, method) for name, url, method in CHECKS]
    payload = {"timestamp": timestamp, "results": results}
    print(json.dumps(payload, ensure_ascii=False))
    failures = [x for x in results if not x["ok"]]
    if failures:
        with open("/tmp/lobster_alert.log", "a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
