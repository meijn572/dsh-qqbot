"""人格 API 投影：只做返回结构，不碰存储。"""
from __future__ import annotations

from memory_core import MemoryStore


def payload(store, data: dict) -> dict:
    data = dict(data or {})
    data["user_profile"] = store.get_user_profile()

    # 渲染收到服务端：人格怎么组织由这里定一次，
    # 消费方（persona.mjs / 复盘 / 面板）直接用 text 或 blocks
    from render import render_persona, render_persona_blocks
    rendered = render_persona(data.get("constitution") or "",
                              data.get("user_profile") or "")

    return {
        "ok": True,
        **data,
        "text": rendered,
        "blocks": render_persona_blocks(data.get("constitution") or "",
                                        data.get("user_profile") or ""),
        "chars": {
            "constitution": len(data["constitution"]),
            "self_model": len(data["self_model"]),
        },
        "limits": {
            "constitution": MemoryStore.CONSTITUTION_MAX,
            "self_model": MemoryStore.SELF_MODEL_MAX,
        },
    }
