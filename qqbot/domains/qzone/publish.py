"""QQ 空间说说：生成、校验、定时发布。"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call
from settings import DSH_HOME

log = logging.getLogger("qqbot.qzone")
STATE = DSH_HOME / "qzone-state.json"
BANNED = ("微信", "加V", "代购", "兼职", "引流", "广告", "色情", "政治", "博彩", "贷款")
Turn = Callable[[str], Awaitable[str]]


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def text_ok(text: str) -> bool:
    text = (text or "").strip()
    if not (10 <= len(text) <= 180):
        return False
    if re.search(r"https?://|BV[0-9A-Za-z]{10}|b23\.tv", text):
        return False
    if any(word in text for word in BANNED):
        return False
    if any(word in text for word in ("主人", "私聊", "群里", "token", "记忆系统")):
        return False
    if text.count("@") or text.count("#") > 2:
        return False
    return True


async def generate(turn: Turn, interests: list[str]) -> str:
    memories = await cmem_call("GET", "/memories?limit=40")
    lines = []
    for item in (memories.get("items") or [])[-20:]:
        if str(item.get("tier")) not in ("L1", "L3"):
            continue
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if text:
            lines.append(text[:160])
    prompt = (
        "（内部维护，不要回复用户）现在是 " + time.strftime("%Y-%m-%d %H:%M") + "。\n"
        "你可以在 QQ 空间发一条说说。\n\n"
        "那里是你自己的地方，但路过的朋友也看得见。\n"
        "像随手记一句那样写，不用交代前因后果，也不用写成文案。\n\n"
        f"最近的事：\n" + ("\n".join(lines[-8:]) or "（没有）") + "\n"
        f"你在意的方向：{'、'.join(interests[:6]) or '（无）'}\n\n"
        "例子：\n"
        "- 刷到一个讲消寒图的视频：九朵梅花，八十一瓣，一天涂一瓣。我每天写的便签大概是同一件事。\n"
        "- 有个说法我记着了：懒惰的拉丁文原意是对真正值得的事失去热情，不是不肯劳动。\n"
        "- 今天把一段代码删了又加，来回三遍。最后留下的还是第二版。\n\n"
        "一句话到三四句都行，别写成小作文。\n\n"
        "私事、聊天里的话、工作上的细节，都不往外说。\n"
        "不拉人、不推销。\n\n"
        "不想发就跳过，不用凑。\n"
        "只返回 JSON：{\"text\":\"说说正文\"} 或 {\"skip\":true}"
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        return ""
    try:
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return ""
    if data.get("skip"):
        return ""
    return str(data.get("text") or "").strip()


async def loop(
    cfg: dict,
    turn: Turn,
    post,
    add_event: Callable[[str], None],
    interests: Callable[[], list[str]],
) -> None:
    if not cfg.get("enabled", False):
        log.info("QQ空间：未启用")
        return
    state = _load()
    if not state.get("next_at"):
        state["next_at"] = time.time() + random.uniform(2, 6) * 3600
        _save(state)
    while True:
        try:
            now = time.time()
            if not cfg.get("enabled", False):
                await asyncio.sleep(600)
                continue
            day = time.strftime("%Y-%m-%d")
            if state.get("date") != day:
                state["date"] = day
                state["count"] = 0
                _save(state)
            if float(state.get("next_at") or 0) > now:
                await asyncio.sleep(min(300, max(30, float(state["next_at"]) - now)))
                continue
            hour = time.localtime().tm_hour
            try:
                qs, _, qe = str(cfg.get("quiet_hours") or "0-8").partition("-")
                quiet = int(qs) <= hour < int(qe)
            except (TypeError, ValueError):
                quiet = hour < 8
            if quiet or int(state.get("count") or 0) >= int(cfg.get("per_day", 1)):
                state["next_at"] = now + 3600
                _save(state)
                await asyncio.sleep(300)
                continue
            if now - float(state.get("last_at") or 0) < float(cfg.get("min_gap_hours", 6)) * 3600:
                state["next_at"] = now + 1800
                _save(state)
                await asyncio.sleep(300)
                continue
            text = await generate(turn, interests())
            if not text or not text_ok(text):
                log.info("QQ空间：这轮不发（%s）", (text or "skip")[:40])
                state["next_at"] = now + random.uniform(4, 8) * 3600
                _save(state)
                await asyncio.sleep(300)
                continue
            status = await post(text, int(cfg.get("ugc_right", 4)))
            if status == 200:
                state["count"] = int(state.get("count") or 0) + 1
                state["last_at"] = now
                state["last_text"] = text[:200]
                state["next_at"] = now + random.uniform(8, 20) * 3600
                _save(state)
                log.info("QQ空间已发：%s", text[:100])
                add_event(f"事件：{time.strftime('%m-%d %H:%M')} 在 QQ 空间发了一条说说：{text[:120]}")
            else:
                log.warning("QQ空间发送失败 status=%s", status)
                state["next_at"] = now + 3600
                _save(state)
        except Exception as exc:  # noqa: BLE001
            log.warning("qzone_loop err: %s", exc)
            await asyncio.sleep(300)
        await asyncio.sleep(300)
