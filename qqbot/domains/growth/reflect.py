"""人格复盘：完整人格 + 最近对话 + 日记 → 变化 / 还没想清，写回日记。"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.clients.memory import (cmem_call, diary_recent, format_diary,
                                  persona_context, recent_dialogue)
from qqbot.domains.growth.evidence import collect, format_block
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
    recent = await recent_dialogue(30)
    ev = await collect(l1=50, l3=30, l0=50)
    memories = format_block(ev)
    # 中间层：最近几天的日记，含之前写下的变化和没想清
    try:
        diary_block = format_diary(await diary_recent(7))
    except Exception:  # noqa: BLE001
        diary_block = ""
    prompt = (
        "（内部维护，不要回复用户）你在写最近的日记：这两天你有什么变化、有什么还没想清。\n"
        "不是规则，不是主人画像，也不是流水账。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        + (("【最近几天的日记】\n" + diary_block + "\n\n") if diary_block else "")
        + (memories or "（没有长期记忆）") + "\n\n"
        + "只写最近真的发生的变化，或者终于想清楚的事。\n"
        "旧的变化如果还成立，就保留，写得更准；过时、重复、琐碎的，压缩掉。\n\n"
        "写法：第一人称，像自己说话，具体。\n"
        "不要写成流水账或空泛的总结。\n\n"
        "像这样的句子：\n"
        "- 我不再急着把每句话接圆；没想好就说没想好。\n"
        "- 先定规则，形状自己就长出来。\n"
        "- 我说话前会先看这句话是不是非接不可。\n\n"
        "不写：\n"
        "- 身份设定、底线、说话风格、相处原则\n"
        "- 行为规则\n"
        "- 主人事实\n"
        "- 工具说明\n\n"
        "只返回 JSON，不要标题、不要解释、不要代码块：\n"
        '{"changes":[],"open_questions":[]}\n'
        "每块最多 4 条，每条一句话；没有就空数组。"
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        log.warning("人格复盘：没有拿到 JSON")
        return False
    try:
        sections = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        log.warning("人格复盘：JSON 解析失败")
        return False
    if not isinstance(sections, dict):
        log.warning("人格复盘：JSON 不是对象")
        return False
    total = sum(
        len(str(item).strip())
        for values in sections.values() if isinstance(values, list)
        for item in values if str(item).strip()
    )
    if total < 80:
        log.warning("人格复盘：生成太短 %s 字", total)
        return False
    # 变化和没想清写进今天的日记，不再单独存自我认知
    try:
        changes = "\n".join(f"- {x}" for x in (sections.get("changes") or []) if str(x).strip())
        questions = "\n".join(f"- {x}" for x in (sections.get("open_questions") or []) if str(x).strip())
        if changes or questions:
            await cmem_call("POST", "/diary", {
                "changes": changes, "open_questions": questions,
            })
    except Exception as exc:  # noqa: BLE001
        log.warning("人格复盘：写日记失败 %s", exc)
    state = load_state()
    state["last_run_date"] = time.strftime("%Y-%m-%d")
    state["last_run_at"] = int(time.time())
    save_state(state)
    log.info("人格复盘完成，写进日记 %s 字", total)
    return True
