"""Phase 0 smoke：检查关键端口和统一接口。

用法：
    python scripts/smoke.py
退出码 0 = 全过，1 = 有失败。
"""
from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))
from settings import CMEM_BASE, PANEL_PORT  # noqa: E402

CHECKS = [
    ("记忆服务 8081", ("127.0.0.1", 8081)),
    ("DSH 60773", ("127.0.0.1", 60773)),
    ("面板 6080", ("127.0.0.1", PANEL_PORT)),
    ("OneBot WS 3001", ("127.0.0.1", 3001)),
]


def tcp_ok(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def http_json(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            body = response.read().decode("utf-8")
            json.loads(body)
            return True, f"{response.status} {len(body)}B"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def http_post_json(url: str, payload: dict) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            json.loads(body)
            return True, f"{response.status} {len(body)}B"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main() -> int:
    failed = 0
    print("== 端口 ==")
    for name, (host, port) in CHECKS:
        ok = tcp_ok(host, port)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failed += 1

    print("== 接口 ==")
    urls = [
        (f"{CMEM_BASE}/persona/context", "GET"),
        (f"{CMEM_BASE}/state", "GET"),
        (f"http://127.0.0.1:{PANEL_PORT}/api/status", "GET"),
        (f"http://127.0.0.1:{PANEL_PORT}/api/persona", "GET"),
        (f"http://127.0.0.1:{PANEL_PORT}/api/memory", "GET"),
        (f"http://127.0.0.1:{PANEL_PORT}/api/lexicon", "GET"),
    ]
    for url, _method in urls:
        ok, detail = http_json(url)
        print(f"[{'PASS' if ok else 'FAIL'}] {url} {detail}")
        if not ok:
            failed += 1

    hooks = [
        (f"{CMEM_BASE}/hook/pre-step", {"messages": []}),
        (f"{CMEM_BASE}/hook/turn-end", {"user": "嗯"}),
    ]
    for url, payload in hooks:
        ok, detail = http_post_json(url, payload)
        print(f"[{'PASS' if ok else 'FAIL'}] POST {url} {detail}")
        if not ok:
            failed += 1

    print(f"\n{'OK' if failed == 0 else f'{failed} FAILED'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
