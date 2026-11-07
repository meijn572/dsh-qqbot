"""人格 API 投影：只做返回结构，不碰存储。"""
from __future__ import annotations

from memory_core import MemoryStore


def payload(store, data: dict) -> dict:
    data = dict(data or {})
    data["user_profile"] = store.get_user_profile()
    return {
        "ok": True,
        **data,
        "chars": {
            "constitution": len(data["constitution"]),
            "self_model": len(data["self_model"]),
        },
        "limits": {
            "constitution": MemoryStore.CONSTITUTION_MAX,
            "self_model": MemoryStore.SELF_MODEL_MAX,
        },
    }
