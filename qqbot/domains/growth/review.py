"""人格复盘：只产核心设定候选，不直接改核心。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call, recent_dialogue
from qqbot.domains.growth.evidence import collect, format_block
from qqbot.domains.growth.proposals import (
    add_proposals,
    load_state,
    recent_history,
    save_state,
)

log = logging.getLogger("qqbot.growth.review")
Turn = Callable[[str], Awaitable[str]]


def _evidence_ids(ev: dict) -> list[str]:
    out = []
    for item in ev.get("items") or []:
        tier = str(item.get("tier") or "")
        mid = item.get("id")
        if tier and mid is not None:
            out.append(f"{tier}:{mid}")
    for row in ev.get("l0") or []:
        mid = row.get("id")
        if mid is not None:
            out.append(f"L0:{mid}")
    return out[:8]


def _clean_ops(raw, target: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:3]:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op") or "add")
        if op not in ("add", "modify", "remove"):
            continue
        if target == "commitment" and op != "add":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        out.append({"op": op, "text": text, "from": str(item.get("from") or "").strip(),
                    "reason": str(item.get("reason") or "").strip()})
    return out


async def run(turn: Turn) -> bool:
    persona = await cmem_call("GET", "/persona")
    constitution = str(persona.get("constitution") or "")
    self_model = str(persona.get("self_model") or "")
    user_profile = str(persona.get("user_profile") or "")
    recent = await recent_dialogue(30)
    ev = await collect(l1=50, l3=30, l0=50)
    memories = format_block(ev)
    history = recent_history()
    prompt = (
        "（内部维护，不要回复用户）做一次核心人格复盘。\n\n"
        "【核心设定】\n" + (constitution or "（空）") + "\n\n"
        "【自我认知】\n" + (self_model or "（空）") + "\n\n"
        "【用户画像】\n" + (user_profile or "（空）") + "\n\n"
        "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        "【长期证据】\n" + (memories or "（没有长期记忆）") + "\n\n"
        "【最近候选】\n" + history + "\n\n"
        "只判断有没有需要修正核心设定里的「判断」「关系」「约定」。\n"
        "不要改身份、性格、边界；不要直接写核心设定。\n"
        "每条必须有最近对话或长期证据支撑；没有就空数组。\n"
        '只返回 JSON，不要解释，不要代码块：\n'
        '{"judgment":[{"op":"add|modify|remove","text":"新内容","from":"旧内容","reason":"依据"}],'
        '"relationship":[{"op":"add|modify|remove","text":"新内容","from":"旧内容","reason":"依据"}],'
        '"commitment":[{"op":"add","text":"一句约定","reason":"依据"}]}\n'
        "每块最多 3 条；没有就 []。"
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        log.warning("人格复盘：没有拿到 JSON")
        return False
    try:
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        log.warning("人格复盘：JSON 解析失败")
        return False
    if not isinstance(data, dict):
        log.warning("人格复盘：JSON 不是对象")
        return False
    evidence = _evidence_ids(ev)
    added = 0
    for target in ("judgment", "relationship", "commitment"):
        ops = _clean_ops(data.get(target), target)
        if ops:
            added += len(add_proposals(target, ops, "人格复盘", evidence))
    state = load_state()
    state["last_run"] = int(time.time())
    save_state(state)
    log.info("人格复盘完成：%s 条候选", added)
    return added > 0
