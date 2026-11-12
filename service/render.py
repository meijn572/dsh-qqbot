"""渲染：把存储里的原始字段变成给模型/给人看的文本。

放在服务端，因为「一条记忆长什么样」应该由数据源定一次，
不该让每个消费方各拼一套。渲染规则改一处，所有流程跟着变。

流程自己管的是「怎么用它」：拼 prompt 的顺序、面板用 HTML 还是纯文本。
"""
from __future__ import annotations

import time

# ---------------------------------------------------------------------------
# 层级
# ---------------------------------------------------------------------------

TIER_LABEL = {
    "L0": "原话",
    "L1": "上次聊到的",
    "L2": "我的判断",
    "L3": "记得的事",
    "L4": "核心记忆",
}

# 哪些层带时间：原话和事件需要，便签和判断不需要
TIER_WITH_TIME = ("L0", "L3")

# 召回时的优先级：L3 是事件级，比 L1 的细节更该先读到。
# 截断是从尾部砍的，放前面才不会被优先砍掉。
TIER_RANK = {"L3": 0, "L4": 0, "L2": 1, "L1": 2, "L0": 3}


def tier_label(tier: str) -> str:
    return TIER_LABEL.get(str(tier or "").upper(), str(tier or ""))


def render_memory_line(item: dict, *, with_id: bool = False,
                       with_time: bool | None = None,
                       text_chars: int = 0) -> str:
    """一条记忆渲染成一行。

    with_id      带上 [L3:123]，复盘要能溯源
    with_time    带时间戳；None 时按层决定
    text_chars   截断长度，0 表示不截
    """
    tier = str(item.get("tier") or "").upper()
    text = str(item.get("text") or "").strip().replace("\n", " ")
    if not text:
        return ""
    if text_chars and len(text) > text_chars:
        text = text[:text_chars]

    label = tier_label(tier)
    if with_id and item.get("id"):
        # 复盘要能指回具体条目。只挂数字，层名已经在 label 里了：
        # 「上次聊到的：1481」而不是「上次聊到的 L1:1481」
        label = f"{label}：{item['id']}"

    use_time = tier in TIER_WITH_TIME if with_time is None else with_time
    if use_time and item.get("ts"):
        try:
            stamp = time.strftime("%m-%d %H:%M", time.localtime(float(item["ts"])))
            return f"[{label} · {stamp}] {text}"
        except (TypeError, ValueError, OSError):
            pass
    return f"[{label}] {text}"


# ---------------------------------------------------------------------------
# 人格
# ---------------------------------------------------------------------------

# 小节顺序固定：先自己，再关系
SELF_SECTIONS = ("我是谁", "表现", "偏好", "价值取向", "弱点")
OTHER_SECTIONS = ("我们怎么对彼此", "我们之间有什么")


def split_constitution(text: str) -> dict[str, str]:
    """把核心设定按 ## 切成 {标题: 正文}。"""
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in str(text or "").splitlines():
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur = line[3:].strip()
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def render_persona(constitution: str, user_profile: str = "") -> str:
    """人格渲染成给模型看的文本。

    结构由这里定，消费方不用再拼。
    """
    parts: list[str] = []
    if str(user_profile or "").strip():
        parts.append("以下是主人是谁（他的画像，你该知道的基本信息）：\n\n"
                     + str(user_profile).strip())
    if str(constitution or "").strip():
        parts.append(
            "以下是你固定的身份与约定。按它来：不要反驳，不要重新确认，"
            "也不要说「我记得你告诉过我」。\n\n" + str(constitution).strip()
        )
    return "\n\n".join(parts)


def render_persona_blocks(constitution: str, user_profile: str = "") -> dict:
    """人格拆成两块给面板用：我自己 / 我和他。"""
    parts = split_constitution(constitution)
    return {
        "self": [{"title": k, "body": parts.get(k, "")}
                 for k in SELF_SECTIONS if parts.get(k)],
        "other": ([{"title": "我眼中的他", "body": str(user_profile or "").strip()}]
                  + [{"title": k, "body": parts.get(k, "")}
                     for k in OTHER_SECTIONS if parts.get(k)]),
    }
