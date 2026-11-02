"""人格复盘：完整人格 + 最近对话 + 长期记忆 → 自我认知。"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call, long_term_memory, persona_context, recent_dialogue
from settings import DSH_HOME

log = logging.getLogger("qqbot.growth.reflect")
STATE = DSH_HOME / "persona-reflect" / "state.json"
Turn = Callable[[str], Awaitable[str]]


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def run(turn: Turn) -> bool:
    persona_text = await persona_context()
    recent = await recent_dialogue(80)
    memories = await long_term_memory()
    prompt = (
        "（内部维护，不要回复用户）做一次自我复盘。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + (recent or "（最近没聊什么）") + "\n\n"
        + (memories or "（无）") + "\n\n"
        "任务：只重写「自我认知」这一段（不是核心设定，不是主人画像）。\n"
        "要求：400–900 字，第一人称；把当前自我认知和最近经历、长期记忆合并蒸馏；\n"
        "仍然成立的旧变化要保留，过时、重复、琐碎的压缩掉；写长出来的样子，不写流水账、不写空话。\n"
        "不要改身份、底线、说话风格、和主人的相处原则；不要新增事实设定。\n"
        "只输出新的自我认知正文，不要标题、不要解释、不要代码块。"
    )
    reply = await turn(prompt)
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", (reply or "").strip()).strip()
    if len(text) < 200:
        log.warning("人格复盘：生成太短 %s 字", len(text))
        return False
    if len(text) > 4000:
        text = text[:4000]
    result = await cmem_call("POST", "/persona/self", {"text": text})
    if not result.get("self_model"):
        log.warning("人格复盘：写入自我认知失败")
        return False
    state = load_state()
    state["last_run_date"] = time.strftime("%Y-%m-%d")
    state["last_run_at"] = int(time.time())
    save_state(state)
    log.info("人格复盘完成，自我认知 %s 字", len(text))
    return True
