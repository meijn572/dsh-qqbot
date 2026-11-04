"""人格分层写入结构：自我认知和用户画像。

模型只交结构化字段，服务端校验并渲染成现有 markdown。
核心设定不经过这里，只走面板半自动保存。
"""
from __future__ import annotations

import re
from typing import Any

SELF_SECTIONS = ("changes", "learned", "open_questions")
PROFILE_SECTIONS = ("stable_facts", "preferences", "values", "interaction", "boundaries")

SELF_TITLES = {
    "changes": "最近的变化",
    "learned": "我学到的",
    "open_questions": "还没想清",
}
PROFILE_TITLES = {
    "stable_facts": "稳定事实",
    "preferences": "偏好",
    "values": "价值与目标",
    "interaction": "互动偏好",
    "boundaries": "边界",
}

SELF_FORBIDDEN = re.compile(r"(回答时|默认|必须|不要|每次|工具名|主人喜欢|主人是)")
PROFILE_FORBIDDEN = re.compile(r"(回答时|默认|你应该|你应当|口癖|人格设定)")


def _clean_list(values: Any, *, limit: int, item_max: int) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("字段必须是数组")
    out = []
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError("数组里只能是字符串")
        text = raw.strip()
        if not text:
            continue
        if len(text) > item_max:
            raise ValueError(f"单条超过 {item_max} 字")
        out.append(text)
        if len(out) >= limit:
            break
    return out


def validate_self_sections(data: Any) -> dict[str, list[str]]:
    if not isinstance(data, dict):
        raise ValueError("sections 必须是对象")
    extra = set(data) - set(SELF_SECTIONS)
    if extra:
        raise ValueError("自我认知不允许字段：" + "、".join(sorted(extra)))
    cleaned = {key: _clean_list(data.get(key), limit=4, item_max=300) for key in SELF_SECTIONS}
    joined = "\n".join(item for values in cleaned.values() for item in values)
    if SELF_FORBIDDEN.search(joined):
        raise ValueError("自我认知里出现了规则/工具/画像内容")
    return cleaned


def render_self_sections(data: dict[str, list[str]]) -> str:
    blocks = []
    for key in SELF_SECTIONS:
        values = data.get(key) or []
        if not values:
            continue
        blocks.append("## " + SELF_TITLES[key] + "\n" + "\n".join("- " + value for value in values))
    return "\n\n".join(blocks)


def validate_profile_sections(data: Any) -> dict[str, list[str]]:
    if not isinstance(data, dict):
        raise ValueError("sections 必须是对象")
    extra = set(data) - set(PROFILE_SECTIONS)
    if extra:
        raise ValueError("画像不允许字段：" + "、".join(sorted(extra)))
    cleaned = {key: _clean_list(data.get(key), limit=12, item_max=300) for key in PROFILE_SECTIONS}
    joined = "\n".join(item for values in cleaned.values() for item in values)
    if PROFILE_FORBIDDEN.search(joined):
        raise ValueError("画像里出现了指令/人格内容")
    return cleaned


def render_profile_sections(data: dict[str, list[str]]) -> str:
    blocks = []
    for key in PROFILE_SECTIONS:
        values = data.get(key) or []
        if not values:
            continue
        blocks.append("**" + PROFILE_TITLES[key] + "**\n" + "\n".join("- " + value for value in values))
    return "\n\n".join(blocks)
