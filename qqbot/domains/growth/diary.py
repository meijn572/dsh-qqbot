"""每日日记：早上 7 点写昨天那一篇。"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from qqbot.clients.memory import cmem_call
from settings import DSH_HOME

log = logging.getLogger("qqbot.growth.diary")
STATE = DSH_HOME / "diary-state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


async def run_once(cfg: dict) -> bool:
    """到点且有素材时写当天日记；返回是否真的发起写入。"""
    if not cfg.get("enabled", True):
        return False
    hour = int(cfg.get("hour", 7))
    if time.localtime().tm_hour < hour:
        return False

    # 写昨天：等当天完整结束，深夜的矛盾不会漏
    import datetime as _dt
    today = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    state = _load_state()
    if state.get("last_date") == today:
        return False

    existing = await cmem_call("GET", "/diary")
    has_today = any(
        str(item.get("date")) == today and str(item.get("text") or "").strip()
        for item in (existing or [])
        if isinstance(item, dict)
    )
    if has_today:
        state["last_date"] = today
        _save_state(state)
        return False

    result = await cmem_call("POST", "/diary", {"date": today})
    if not result.get("ok"):
        log.warning("日记写入失败：%s", result.get("error") or result)
        return False
    state["last_date"] = today
    _save_state(state)
    log.info("日记已写：%s 字", len(str(result.get("text") or "")))
    return True


async def loop(cfg: dict) -> None:
    await asyncio.sleep(90)
    while True:
        try:
            await run_once(cfg)
        except Exception as exc:  # noqa: BLE001
            log.warning("diary_loop err: %s", exc)
        await asyncio.sleep(15 * 60)
