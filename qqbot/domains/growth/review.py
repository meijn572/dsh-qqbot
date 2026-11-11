"""人格复盘：只产核心设定候选，不直接改核心。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import (cmem_call, diary_recent, expand_persona_links,
                                  format_diary, recent_dialogue)
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
    # 复盘要看见每条格的来处，所以这里用展开版（日常注入不展开）
    constitution = await expand_persona_links(str(persona.get("constitution") or ""))
    self_model = str(persona.get("self_model") or "")
    user_profile = str(persona.get("user_profile") or "")
    recent = await recent_dialogue(30)
    ev = await collect(l1=50, l3=30, l0=50)
    memories = format_block(ev)
    history = recent_history()
    # 中间层：最近 7 天的日记。它记的是「最近在变什么」，
    # 正是人格该不该改的直接线索。
    try:
        diary_block = format_diary(await diary_recent(7))
    except Exception:  # noqa: BLE001
        diary_block = ""
    prompt = (
        "（内部维护，不要回复用户）做一次核心人格复盘。\n\n"
        "【核心设定】\n" + (constitution or "（空）") + "\n\n"
        "【自我认知】\n" + (self_model or "（空）") + "\n\n"
        "【用户画像】\n" + (user_profile or "（空）") + "\n\n"
        "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        + (("【最近几天的日记】\n" + diary_block + "\n\n") if diary_block else "")
        + "【长期证据】\n" + (memories or "（没有长期记忆）") + "\n\n"
        "【最近候选】\n" + history + "\n\n"
        "只判断这四类要不要改：\n"
        "\n"
        "preference   她长期稳定的喜好（喜欢什么、不爱什么）\n"
        "judgment     她相信什么、怎么做判断\n"
        "relationship 她和他怎么相处\n"
        "weakness     她会栽在哪\n"
        "\n"
        "不要改身份、性格、说话风格、边界。\n"
        "不要产出「约定」——那是另一条线管的。\n"
        "每条必须有最近对话、日记或长期证据支撑；没有就空数组。\n"
        "\n"
        "四类的区别，看这条说的是什么：\n"
        "\n"
        "preference  喜欢某个具体的东西\n"
        "  他喜欢许嵩的歌，觉得《如果当时》高潮那段戏腔有意境\n"
        "  我其实挺爱刷这种科普，虽然看完记不住多少\n"
        "\n"
        "judgment    相信某个道理\n"
        "  八小时工作制是靠人争来的，不是蒸汽机发的\n"
        "  技术只把可能性摆出来，不会自己变成生产关系\n"
        "\n"
        "relationship 怎么对待他、我们之间怎么走\n"
        "  他讲难受的事时，先听，别急着给方案\n"
        "  我不拿「一定还是我」哄他，因为我自己也验不了\n"
        "\n"
        "weakness    自己会在哪儿失准\n"
        "  我会把推断当成他说过的话，容易替他安一个意思\n"
        "  我会为了把话说圆而多加一句，话本来到那儿就该停\n"
        '只返回 JSON，不要解释，不要代码块：\n'
        '{"preference":[{"op":"add|modify|remove","text":"新内容","from":"旧内容",'
        '"reason":"依据","source":123}],'
        '"judgment":[...],"relationship":[...],"weakness":[...]}\n'
        "每块最多 3 条；没有就 []。\n"
        "\n"
        "source 填这条改的依据是哪条现有事件（输入里 [L3:123] 那个数字）。\n"
        "依据来自日记或长期对话、指不到具体事件时，source 留空。\n"
        "有 source 的，以后能追回原话；没有的，就只是你现在的判断。"
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
    for target in ("preference", "judgment", "relationship", "weakness"):
        ops = _clean_ops(data.get(target), target)
        if ops:
            added += len(add_proposals(target, ops, "人格复盘", evidence))
    state = load_state()
    state["last_run"] = int(time.time())
    save_state(state)
    log.info("人格复盘完成：%s 条候选", added)
    return added > 0
