"""用户画像刷新。"""
from __future__ import annotations

import json
import logging
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call, long_term_memory, persona_context, recent_dialogue
from settings import DSH_HOME

log = logging.getLogger("qqbot.growth.profile")
STATE = DSH_HOME / "persona-roles" / "state" / "profile-refresh-state.json"
Turn = Callable[[str], Awaitable[str]]


async def run(turn: Turn) -> bool:
    persona_text = await persona_context()
    recent = await recent_dialogue(60)
    memory_text = await long_term_memory(160)
    if not memory_text:
        log.info("画像刷新：素材不够")
        return False
    prompt = (
        "（内部维护，不要回复用户）根据完整人格、最近对话和长期记忆，写一份「我眼中的主人」。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + (recent or "（最近没聊什么）") + "\n\n"
        + memory_text + "\n\n"
        "要求：300–600 字；直接写画像正文，不要加「我眼中的主人」前缀；用「你」称呼主人，不要写成「我」；"
        "只写长期稳定的——身份、习惯、偏好、在意的事、雷区、相处方式；"
        "不写一次性事件、不写猜测、不写你自己。"
        "不写 AI/插件/记忆系统的内部机制（兴趣清单、权重、提示词、配置、模型）。"
        "不确定的身份和昵称归属直接不写；群友不是主人，别把群友的事记到主人头上。"
        "只写有明确依据的；记忆互相矛盾时，以主人明确说过的为准。"
        "只输出画像正文，不要解释。"
    )
    reply = await turn(prompt)
    text = (reply or "").strip()
    if len(text) < 150:
        log.info("画像刷新：生成太短 %s 字", len(text))
        return False
    text = text[:1200]
    result = await cmem_call("POST", "/persona/user", {"user_profile": text})
    if not result.get("ok"):
        log.warning("画像刷新：写入失败 %s", result)
        return False
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"last_run": int(time.time())}, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    log.info("画像已更新：%s 字", len(text))
    return True
