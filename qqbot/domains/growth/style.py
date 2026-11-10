"""表达风格复盘：只生成待确认提议，不自动改核心设定。"""
from __future__ import annotations

import difflib
import json
import logging
import re
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import bili_insights, cmem_call, persona_context, recent_dialogue
from qqbot.domains.growth.evidence import collect, format_block
from settings import DSH_HOME

log = logging.getLogger("qqbot.growth.style")
STYLE_BEGIN = "<!-- style:begin -->"
STYLE_END = "<!-- style:end -->"
PROPOSAL = DSH_HOME / "persona-roles" / "state" / "style-proposal.json"
STATE = DSH_HOME / "persona-roles" / "state" / "style-review-state.json"
Turn = Callable[[str], Awaitable[str]]


def style_block(constitution: str) -> str:
    text = str(constitution or "")
    match = re.search(re.escape(STYLE_BEGIN) + r"(.*?)" + re.escape(STYLE_END), text, re.S)
    if match:
        return match.group(1).strip()
    match = re.search(r"## 表现\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    return match.group(1).strip() if match else ""


def _similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.95


async def run(turn: Turn, chat_key: str) -> bool:
    persona = await cmem_call("GET", "/persona")
    current = style_block(str(persona.get("constitution") or ""))
    if not current:
        log.warning("风格复盘：核心设定里没有 style 标记")
        return False
    persona_text = await persona_context()
    recent = await recent_dialogue(60)
    ev = await collect(l1=30, l3=20, l0=30)
    material = format_block(ev) or "（没有足够素材）"
    insights = await bili_insights("style", limit=12, days=90)
    insight_block = "\n".join(f"- {x.get('insight_text')}" for x in insights if x.get("insight_text"))
    prompt = (
        "（内部维护，不要回复用户）只调整她的「表达风格」，不要改身份、底线和相处原则。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + "【当前风格】\n" + current + "\n\n"
        + "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        + material + "\n\n"
        + (("【看视频时留下的表达观察】\n" + insight_block + "\n\n") if insight_block else "")
        + "任务：结合完整人格、最近相处和长期记忆，判断她的说话方式有没有自然变化，写出更新后的风格段。\n"
        "保留仍然成立的部分，只改真正有变化的。\n\n"
        "例子：\n"
        "旧：\n"
        "- 说话简洁，结论先说。\n"
        "- 不绕弯子。\n\n"
        "新：\n"
        "- 说话简洁，结论先说。\n"
        "- 不绕弯子。\n"
        "- 他难受的时候先停一下，不急着给方案。\n\n"
        "4–10 条短句，总长 120–500 字。\n"
        "不要新增身份/事实/关系设定，不要写成规则说明书。\n"
        '只返回 JSON：{"style":"- …\\n- …","reason":"为什么改，一句话"}'
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        log.warning("风格复盘：模型没给 JSON，回复：%s", (reply or "")[:400])
        return False
    try:
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return False
    style = str(data.get("style") or "").strip()
    reason = str(data.get("reason") or "").strip()
    if not (100 <= len(style) <= 600):
        log.warning("风格复盘：长度不合适 %s", len(style))
        return False
    bullets = [line for line in style.splitlines() if line.strip().startswith("- ")]
    if not (4 <= len(bullets) <= 10):
        log.warning("风格复盘：条数不合适 %s", len(bullets))
        return False
    if _similar(style[:60], current[:60]) and abs(len(style) - len(current)) < 20:
        log.info("风格复盘：变化太小，不生成提议")
        return False
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    PROPOSAL.write_text(json.dumps(
        {"style": style, "reason": reason, "base": current, "ts": int(time.time())},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("风格复盘：已生成提议 %s 字", len(style))
    return True
