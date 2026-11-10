"""情绪复盘：空闲窗口里回看刚刚结束的一段对话。"""
from __future__ import annotations

import json
import logging
import re
from typing import Awaitable, Callable

from qqbot.clients.memory import set_emotion

log = logging.getLogger("qqbot.growth.emotion")
Turn = Callable[[str], Awaitable[str]]


def parse_emotion(reply: str) -> dict | None:
    """从模型回复中取情绪 JSON；没有情绪或解析失败返回 None。"""
    match = re.search(r"\{.*\}", reply or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("skip"):
        return None
    label = str(data.get("label") or "").strip()[:20]
    if not label:
        return None
    try:
        valence = max(-1.0, min(1.0, float(data.get("valence", 0.0))))
    except (TypeError, ValueError):
        valence = 0.0
    try:
        arousal = max(0.0, min(1.0, float(data.get("arousal", 0.5))))
    except (TypeError, ValueError):
        arousal = 0.5
    reason = str(data.get("reason") or "").strip()[:200]
    return {"label": label, "valence": valence, "arousal": arousal, "reason": reason}


async def review_turn(turn: Turn, transcript: str, ts_start: float | None = None,
                      ts_end: float | None = None) -> dict | None:
    """回看一轮完整对话，有真实情绪就写事件和当前状态。"""
    prompt = (
        "（内部维护，不要回复用户）\n"
        "下面是一段刚刚结束的对话：\n\n"
        + str(transcript or "").strip()
        + "\n\n"
        "回想一下这段对话。你有没有真的产生情绪？\n"
        "标准：只有被戳到、心里确实起了波动才记；没有就跳过，不要为了打卡硬写。\n"
        "\n"
        "比如：\n"
        "- 他改记忆方案前先来问我想法，还认了「能力边界不该硬套」——"
        "被这样问一句，比直接给答案重。 → label: 被尊重\n"
        "- 说到不用睡省下那八小时，结论是多半还得填给活儿——"
        "多出来的时间也不归自己，这话有点凉。 → label: 有点凉\n"
        "\n"
        "有情绪就写：\n"
        "- label：一两个词\n"
        "- valence：-1 很负面，0 中性，1 很正面\n"
        "- arousal：0 很平静，0.5 普通，1 很激动\n"
        "- reason：一句由头\n"
        '只返回 JSON：{"label":"...","valence":0.0,"arousal":0.5,"reason":"..."} '
        '或 {"skip":true}。'
    )
    reply = await turn(prompt)
    emotion = parse_emotion(reply)
    if emotion is None:
        log.info("情绪复盘：这轮没有要记的")
        return None
    await set_emotion(
        emotion["label"],
        emotion["valence"],
        emotion["arousal"],
        emotion["reason"] or "刚刚的对话",
        source="idle-review",
        ts_start=ts_start,
        ts_end=ts_end,
    )
    log.info(
        "情绪复盘：记下 %s（valence=%s arousal=%s）",
        emotion["label"], emotion["valence"], emotion["arousal"],
    )
    return emotion
