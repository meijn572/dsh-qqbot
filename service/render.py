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

# 状态给人话。模型看到「open」这种词会当成变量名复述出来。
# 只给「标题没说到」的状态加注。open 不加：那节标题已经写了「还没完的事」，
# 每行再挂一次等于重复。这条清单也只收 open 的，其它状态本来就不该出现。
STATUS_SPOKEN = {
    "closed": "已经完了",
    "dormant": "很久没提了",
    "standalone": "",
    "open": "",
}

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
        # 复盘要能指回具体条目（source 字段要填这个数字）。
        # 用括注而不是冒号，读起来像注解，不像编号：「上次聊到的（1481）」
        label = f"{label}（{item['id']}）"

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


# 人格里的【L3:123】是溯源标记，给面板和复盘看。
# 模型看到会诱发「你那次说过……」这类逐句复述，所以在渲染时抹掉。
import re as _re
_PERSONA_LINK = _re.compile(r"\s*【L3:\d+】")


def strip_persona_links(text: str) -> str:
    return _PERSONA_LINK.sub("", str(text or ""))


def render_persona(constitution: str, user_profile: str = "") -> str:
    """人格渲染成给模型看的文本。

    结构由这里定，消费方不用再拼。
    【L3:】 在这里就去掉，消费方不用各自过滤一遍。
    """
    constitution = strip_persona_links(constitution)
    user_profile = strip_persona_links(user_profile)
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

# ---------------------------------------------------------------------------
# 中间层（日记）
# ---------------------------------------------------------------------------

# 日记各段的标题。顺序固定：先当天，再变化，再没想清，最后关系
DIARY_FIELDS = (
    ("text", ""),
    ("changes", "变化"),
    ("open_questions", "还没想清"),
    ("relationship", "那天的关系"),
)


def render_diary_row(row: dict) -> str:
    """一天渲染成一块；没内容返回空串。"""
    parts: list[str] = []
    for key, title in DIARY_FIELDS:
        body = str(row.get(key) or "").strip()
        if not body:
            continue
        parts.append(f"{title}：\n{body}" if title else body)
    if not parts:
        return ""
    return f"【{row.get('date') or ''}】\n" + "\n".join(parts)


def render_diary(rows: list[dict]) -> str:
    """多天拼一起，空行分隔。"""
    blocks = [b for b in (render_diary_row(r) for r in (rows or [])) if b]
    return "\n\n".join(blocks)

# ---------------------------------------------------------------------------
# 状态块
# ---------------------------------------------------------------------------

def render_time_block(ts, week=None) -> str:
    """现在是 2026-11-12 周四 22:30（深夜）。"""
    lt = time.localtime(ts)
    hh = lt.tm_hour
    weekdays = week or ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    date_str = time.strftime("%Y-%m-%d", lt) + f" {weekdays[lt.tm_wday]} {hh:02d}:{lt.tm_min:02d}"
    phase = ("凌晨" if hh < 5 else "清早" if hh < 8 else "上午" if hh < 11
             else "中午" if hh < 13 else "下午" if hh < 17
             else "傍晚" if hh < 19 else "晚上" if hh < 22 else "深夜")
    return f"现在是 {date_str}（{phase}）。"


def render_sleepy_block(hour: int) -> str:
    """按小时给困意提示；白天返回空串。"""
    if hour >= 23 or hour < 6:
        return "你现在困得眼睛都睁不开了，回话短一点、慢一点，别硬撑。"
    if hour >= 21:
        return "有点困了，说话懒一点。"
    return ""


def render_open_threads(threads: list[dict]) -> str:
    """还没完的事：只给标题和状态。"""
    lines = []
    for t in (threads or [])[:8]:
        title = str(t.get("title") or "").strip()
        if not title:
            continue
        # 状态翻成人话，没状态或片段就只说事本身
        note = STATUS_SPOKEN.get(str(t.get("status") or "").strip().lower(), "")
        lines.append(f"- {title}（{note}）" if note else f"- {title}")
    return "【还没完的事】\n" + "\n".join(lines) if lines else ""


def render_relationship(summary: str) -> str:
    s = str(summary or "").strip()
    return f"最近我们的关系：{s}" if s else ""
