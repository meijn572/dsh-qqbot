"""情绪自检：定时让模型自己判断有没有真实情绪。"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.clients.memory import l0_recent, set_emotion
from settings import DSH_HOME, OWNER_CHAT_KEY

log = logging.getLogger("qqbot.growth.emotion")
STATE = DSH_HOME / "emotion-check-state.json"
Turn = Callable[[str], Awaitable[str]]


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _save(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def loop(turn: Turn, cfg: dict) -> None:
    if not cfg.get("enabled", False):
        log.info("情绪自检：未启用")
        return
    state = _load()
    if not state.get("next_at"):
        state["next_at"] = time.time() + random.uniform(5, 10) * 60
        _save(state)
    while True:
        try:
            if not cfg.get("enabled", False):
                await asyncio.sleep(300)
                continue
            now = time.time()
            day = time.strftime("%Y-%m-%d")
            if state.get("date") != day:
                state["date"] = day
                state["count"] = 0
                _save(state)
            if float(state.get("next_at") or 0) > now:
                await asyncio.sleep(min(600, max(30, float(state["next_at"]) - now)))
                continue
            hour = time.localtime().tm_hour
            try:
                qs, _, qe = str(cfg.get("quiet_hours") or "0-8").partition("-")
                quiet = int(qs) <= hour < int(qe)
            except (TypeError, ValueError):
                quiet = hour < 8
            if quiet or int(state.get("count") or 0) >= int(cfg.get("per_day", 5)):
                state["next_at"] = now + 3600
                _save(state)
                await asyncio.sleep(300)
                continue
            recent = await l0_recent(OWNER_CHAT_KEY, 40) or "（最近没聊什么）"
            prompt = (
                "（内部维护，不要回复用户）现在是 " + time.strftime("%Y-%m-%d %H:%M") + "。\n"
                "回想一下最近这段相处。\n\n"
                f"【最近】\n{recent}\n\n"
                "你有没有真的产生情绪？标准：只有被戳到、心里确实起了波动才记；"
                "没有就跳过，不要为了打卡硬写。\n"
                "有情绪就写 label（一两个词）、intensity（0–1）、reason（一句由头）。\n"
                '只输出 JSON：{"label":"...","intensity":0.5,"reason":"..."} 或 {"skip":true}。'
            )
            reply = await turn(prompt)
            match = re.search(r"\{.*\}", reply or "", re.S)
            data = {}
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:  # noqa: BLE001
                    data = {}
            label = str(data.get("label") or "").strip()[:20]
            reason = str(data.get("reason") or "").strip()[:200]
            try:
                intensity = max(0.0, min(1.0, float(data.get("intensity") or 0.5)))
            except (TypeError, ValueError):
                intensity = 0.5
            if not label or data.get("skip"):
                log.info("情绪自检：这轮没有要记的")
            else:
                positive = bool(re.search(r"(开心|高兴|喜欢|温柔|感动|兴奋|甜|满意|期待|放松|骄傲|暖|被夸|幸福|好笑|笑|乐|有趣)", label))
                valence = intensity if positive else -intensity
                await set_emotion(label, valence, 0.5, reason or "自己回想的")
                state["count"] = int(state.get("count") or 0) + 1
                state["last_label"] = label
                log.info("情绪自检：记下 %s（%s）", label, reason[:40])
            state["next_at"] = now + random.uniform(float(cfg.get("min_hours", 3)), float(cfg.get("max_hours", 5))) * 3600
            _save(state)
        except Exception as exc:  # noqa: BLE001
            log.warning("emotion_check err: %s", exc)
            state["next_at"] = time.time() + 3600
            _save(state)
        await asyncio.sleep(300)
