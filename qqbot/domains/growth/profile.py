"""用户画像刷新。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call, persona_context, recent_dialogue
from qqbot.domains.growth.evidence import collect, format_block
from settings import DSH_HOME

log = logging.getLogger("qqbot.growth.profile")
STATE = DSH_HOME / "persona-roles" / "state" / "profile-refresh-state.json"
Turn = Callable[[str], Awaitable[str]]


async def run(turn: Turn) -> bool:
    persona_text = await persona_context()
    recent = await recent_dialogue(20)
    ev = await collect(l1=50, l3=30, l0=50)
    memory_text = format_block(ev)
    if not memory_text:
        log.info("画像刷新：素材不够")
        return False
    prompt = (
        "（内部维护，不要回复用户）根据完整人格、最近对话和长期记忆，整理一份「我眼中的主人」。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        + memory_text + "\n\n"
        "只输出 JSON，不要解释，不要代码块：\n"
        '{"stable_facts":["长期稳定的身份/习惯"],'
        '"preferences":["喜欢/不喜欢/娱乐偏好"],'
        '"values":["价值与目标"],'
        '"interaction":["他希望怎么被回应"],'
        '"boundaries":["明确的雷区和边界"]}\n'
        "要求：只用「主人/他」称呼，不写「你」；每条一句话，具体、有依据；"
        "不写一次性事件、不写猜测、不写你自己；"
        "不写 AI/插件/记忆系统/提示词/配置/模型；"
        "群友不是主人；不确定的身份和昵称归属直接不写；"
        "没有内容的 section 用空数组。"
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        log.info("画像刷新：没有拿到 JSON")
        return False
    try:
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        log.info("画像刷新：JSON 解析失败")
        return False
    if not isinstance(data, dict):
        log.info("画像刷新：JSON 不是对象")
        return False
    total = sum(
        len(str(item).strip())
        for values in data.values() if isinstance(values, list)
        for item in values if str(item).strip()
    )
    if total < 80:
        log.info("画像刷新：内容太短 %s 字", total)
        return False
    result = await cmem_call("POST", "/persona/user", {"sections": data})
    if not result.get("ok"):
        log.warning("画像刷新：写入失败 %s", result)
        return False
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"last_run": int(time.time())}, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    log.info("画像已更新：%s 字", total)
    return True
