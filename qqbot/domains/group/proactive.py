"""群主动说话：时机、生成、发送、冷却。"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Awaitable, Callable

log = logging.getLogger("qqbot.group.proactive")
STATE: dict[str, dict] = {}


def _quiet(value: str) -> tuple[int, int]:
    try:
        a, _, b = str(value or "0-8").partition("-")
        return int(a), int(b)
    except (TypeError, ValueError):
        return 0, 8


def _strip_skip(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    lines = [line for line in lines if line.upper() != "SKIP" and not line.startswith("SKIP")]
    return "\n".join(lines).strip()


async def say(
    *,
    groups: list,
    turn: Callable[[str], Awaitable[str]],
    send: Callable[[str], Awaitable[None]],
    add_l0: Callable[[str], None],
    history: Callable[[str], list[dict]],
    mark_active: Callable[[str], None],
) -> str | None:
    if not groups:
        return None
    gid = int(groups[0])
    chat_key = f"group:{gid}"
    recent = history(chat_key)[-8:]
    convo = "\n".join(f"{item['user']}: {item['text']}" for item in recent)
    prompt = (
        "（这是群聊，不是私聊）最近群里聊了：\n"
        + (convo or "（还没人说话）")
        + "\n你是群里的大肥鱼。有没有想接一句、或者自己说一句的？"
        "想说什么就自然说一两句；没话就只回 SKIP 两个字母。别艾特人，别解释。"
    )
    try:
        reply = await turn(prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("group proactive 失败: %s", exc)
        return None
    text = _strip_skip(reply)
    if not text:
        log.info("群主动：这次没话说")
        return None
    if len(text) > 300:
        text = text[:300] + "……"
    await send(text)
    add_l0(text)
    state = STATE.setdefault(chat_key, {"date": time.strftime("%Y-%m-%d"), "count": 0, "last": 0})
    today = time.strftime("%Y-%m-%d")
    if state.get("date") != today:
        state.update({"date": today, "count": 0})
    state["count"] = int(state.get("count", 0)) + 1
    state["last"] = time.time()
    mark_active(chat_key)
    log.info("群主动开口：%s", text[:120])
    return text


async def loop(
    *,
    cfg: dict,
    groups: list,
    turn: Callable[[str], Awaitable[str]],
    send: Callable[[str], Awaitable[None]],
    add_l0: Callable[[str], None],
    history: Callable[[str], list[dict]],
    mark_active: Callable[[str], None],
    seen: Callable[[str], float],
) -> None:
    if not cfg.get("enabled", True):
        log.info("群主动：未启用")
        return
    lo = max(10, int(cfg.get("min_minutes", 90)))
    hi = max(lo, int(cfg.get("max_minutes", 180)))
    log.info("群主动：已启用，间隔 %s-%s 分钟", lo, hi)
    while True:
        await asyncio.sleep(random.randint(lo, hi) * 60)
        start, end = _quiet(cfg.get("quiet_hours", "0-8"))
        hour = time.localtime().tm_hour
        if (start <= end and start <= hour < end) or (start > end and (hour >= start or hour < end)):
            continue
        if not groups:
            continue
        chat_key = f"group:{int(groups[0])}"
        if time.time() - seen(chat_key) < float(cfg.get("idle_minutes", 30)) * 60:
            continue
        state = STATE.setdefault(chat_key, {"date": time.strftime("%Y-%m-%d"), "count": 0, "last": 0})
        if state.get("date") != time.strftime("%Y-%m-%d"):
            state.update({"date": time.strftime("%Y-%m-%d"), "count": 0})
        if int(state.get("count", 0)) >= int(cfg.get("daily_max", 2)):
            continue
        try:
            await say(
                groups=groups, turn=turn, send=send, add_l0=add_l0,
                history=history, mark_active=mark_active,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("group proactive loop err: %s", exc)
