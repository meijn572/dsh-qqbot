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
        "（内部维护，不要回复用户）你写「我眼中的主人」。\n\n"
        + (persona_text or "（空）") + "\n\n"
        + "【最近对话】\n" + (recent or "（最近没聊什么）") + "\n\n"
        + memory_text + "\n\n"
        "只写过几个月回看还成立的东西。\n"
        "今天、这几天、这一阵才成立的，留在最近对话里，不写进画像。\n\n"
        "四个部分，按「这是什么」分，不按话题分：\n"
        "stable_facts  他是谁：身份、处境、做过什么\n"
        "appearance    他平时什么样子：作息、说话方式、遇事的习惯动作\n"
        "preferences   长期喜欢/不喜欢什么（内容、玩法、被怎么对待）\n"
        "values        他相信什么：判断和取舍，不写做法\n\n"
        "分不清的时候问一句：\n"
        "  「他每天/每次都这样」     → appearance\n"
        "  「他喜欢/讨厌某个东西」   → preferences\n"
        "  「他认为世界是怎么回事」 → values\n\n"
        "「他怎么被回应」和「边界」不要写进来——那些属于我们怎么相处，\n"
        "不是他是谁。\n\n"
        "每条一句话，具体、有依据。\n\n"
        "例子：\n"
        "stable_facts\n"
        "- 主人晚睡，凌晨两三点睡、上午十一点起\n"
        "- 主人深夜写代码最顺，白天总被打断\n\n"
        "appearance\n"
        "- 主人说话短，结论先说\n"
        "- 主人刷到东西先掂量有没有依据，只靠耸动数字撑起来的直接划掉\n\n"
        "preferences\n"
        "- 主人喜欢许嵩的歌，觉得《如果当时》高潮那段的戏腔很有意境\n"
        "- 主人常看 KPL，看比赛希望有人陪着\n\n"
        "values\n"
        "- 主人认为优秀和吃苦只是换甜的手段，终点是三十岁攒够钱退休\n"
        "- 主人认为让人变强靠鼓励，不靠压力\n\n"
        "称呼用「主人/他」；群友不是主人。\n"
        "不写 AI/插件/记忆系统/提示词/配置/模型。\n"
        "没有内容就空数组。\n\n"
        "只返回 JSON，不要解释，不要代码块：\n"
        '{"stable_facts":[],"appearance":[],"preferences":[],"values":[]}'
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
