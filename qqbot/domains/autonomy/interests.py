"""兴趣提取与合并。"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Awaitable, Callable

from qqbot.clients.memory import l0_recent
from qqbot.domains.autonomy.bili import apply_interest
from qqbot.domains.autonomy.state import (
    autonomy_cfg,
    load_aut_state,
    load_interests,
    read_new_l1,
    save_aut_state,
    save_interests,
    similar_topic,
)

log = logging.getLogger("qqbot.autonomy.interests")
Turn = Callable[[str], Awaitable[str]]


async def extract(turn: Turn, chat_key: str, text: str) -> None:
    cfg = autonomy_cfg()
    if not cfg.get("enabled", True) or len(text.strip()) < 8:
        return
    state = load_aut_state()
    if time.time() - float(state.get("last_extract") or 0) < 600:
        return
    cursor = int(state.get("interest_l1_rowid") or 0)
    rows, top_rowid = read_new_l1(cursor, 12)
    memories = [(row[1], row[2]) for row in rows]
    mem_lines = "\n".join(f"[M{index + 1}] {content}" for index, (_, content) in enumerate(memories[:8]))
    recent = await l0_recent(chat_key, 12)
    if not memories and not recent:
        return
    existing = "、".join(str(i.get("topic", "")) for i in load_interests()[:20]) or "（还没有）"
    prompt = (
        "（内部记录，不要回复用户）最近对话（节选，可能跨群和私聊）：\n" + (recent or "（无）") + "\n\n"
        "最近新增的长期记忆：\n" + (mem_lines or "（无）") + "\n\n"
        f"已有兴趣清单：{existing}\n"
        "从上面的对话和记忆里，提取主人或你自己在意的具体话题（游戏、番剧、技术、事件、人物均可）。\n"
        "重要：如果说的就是清单里某个已有话题（哪怕说法不同），**必须直接复用那个已有话题的名字**，只给 delta；"
        "只有确实是全新的话题才起新名字，新名字用 ≤12 字的短标签。\n"
        "如果某个话题有对应的记忆编号，把 [M1] 这类编号填进 memory；没有就留空数组。\n"
        '只输出 JSON 数组：[{"topic":"话题","delta":1,"evidence":"依据","memory":["M1"]}]; 没有话题就输出 []。不要输出别的。'
    )
    reply = await turn(prompt)
    match = re.search(r"\[.*\]", reply, re.S)
    if not match:
        return
    try:
        items = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return
    seen_topics: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        if any(similar_topic(topic, seen) for seen in seen_topics):
            continue
        seen_topics.append(topic)
        ids: list[str] = []
        for tag in item.get("memory") or []:
            found = re.fullmatch(r"M?(\d+)", str(tag).strip(), re.I)
            if found:
                index = int(found.group(1)) - 1
                if 0 <= index < len(memories):
                    ids.append(memories[index][0])
        if not ids and memories:
            grams = {topic[i:i + 2] for i in range(len(topic) - 1) if len(topic[i:i + 2]) == 2}
            for record_id, content in memories[:8]:
                text_value = str(content)
                if grams and sum(1 for gram in grams if gram in text_value) >= max(1, len(grams) // 3):
                    ids.append(record_id)
            ids = ids[:3]
        apply_interest(topic, float(item.get("delta") or 1), str(item.get("evidence", "")), "chat", ids)
    state = load_aut_state()
    state["last_extract"] = int(time.time())
    if rows:
        state["interest_l1_rowid"] = top_rowid
    save_aut_state(state)
    log.info("兴趣已更新：%s", [i.get("topic") for i in load_interests()[:5]])


async def consolidate(turn: Turn, chat_key: str) -> None:
    items = load_interests()
    if len(items) < 3:
        return
    listing = "\n".join(f"- {i.get('topic')}（权重 {i.get('weight')}）" for i in items)
    prompt = (
        "（内部维护，不要回复用户）下面是兴趣清单。把说的是同一件事的主题合并成组：\n" + listing + "\n\n"
        "只输出 JSON 数组，每组第一个是保留的名字（尽量用现有的短名字），后面是要并进它的同义主题，"
        "必须与清单里的名字逐字一致；不需要合并的不要列。\n"
        '示例：[["王者荣耀","王者卡段位","连跪之后到底该怪什么"]]；没有可合并的就输出 []。不要输出别的。'
    )
    reply = await turn(prompt)
    match = re.search(r"\[.*\]", reply or "", re.S)
    if not match:
        return
    try:
        groups = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return
    changed = False
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, list) or len(group) < 2:
            continue
        names = [str(n).strip() for n in group if str(n).strip()]
        if len(names) < 2:
            continue
        target = next((i for i in items if similar_topic(names[0], str(i.get("topic", "")))), None)
        if target is None:
            continue
        for name in names[1:]:
            member = next((i for i in items if i is not target and similar_topic(name, str(i.get("topic", "")))), None)
            if member is None:
                continue
            target["weight"] = round(min(9.0, float(target.get("weight", 1)) + float(member.get("weight", 1)) * 0.5), 2)
            if member.get("evidence") and not target.get("evidence"):
                target["evidence"] = member["evidence"]
            target["last_seen"] = max(int(target.get("last_seen") or 0), int(member.get("last_seen") or 0))
            items.remove(member)
            changed = True
    if changed:
        items.sort(key=lambda x: float(x.get("weight", 0)), reverse=True)
        save_interests(items[:40])
        log.info("兴趣合并完成：%s", [i.get("topic") for i in items[:10]])
