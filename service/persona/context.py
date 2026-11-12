"""人格块格式。

复盘（reflect / review / style / profile / important）都读这个。
渲染统一走 render.render_persona，不再自己拼一份。
"""
from __future__ import annotations


def build_persona_context(persona: dict, keep_links: bool = True) -> dict:
    """人格渲染成复盘看的文本。

    keep_links=True 时保留 【L3:123】 溯源标记 —— 复盘要能指回具体事件。
    日常注入（persona.mjs）走的是 /persona 的 text，那里已经抹掉了标记。
    """
    from render import render_persona, strip_persona_links

    constitution = str(persona.get("constitution") or "")
    profile = str(persona.get("user_profile") or "")
    text = render_persona(
        constitution if keep_links else strip_persona_links(constitution),
        profile if keep_links else strip_persona_links(profile),
    )
    return {"ok": True, "text": text}
