"""记忆/人格服务的 HTTP 客户端。

桥接和 growth 只通过这里访问记忆服务，不自己拼 URL。
"""
from __future__ import annotations

import json
from pathlib import Path

import aiohttp

from settings import CMEM_BASE, DSH_HOME, OWNER_CHAT_KEY


async def cmem_call(method: str, path: str, body: dict | None = None) -> dict:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        kwargs = {"json": body} if body is not None else {}
        async with session.request(method, CMEM_BASE + path, **kwargs) as resp:
            return await resp.json(content_type=None)


async def persona_context() -> str:
    data = await cmem_call("GET", "/persona/context")
    return str(data.get("text") or "")


async def long_term_memory(limit: int = 160) -> str:
    data = await cmem_call("POST", "/context", {
        "tiers": {"L1": 80, "L2": 10, "L3": 40, "L4": 10},
        "purpose": "review",
        "max_chars": 16000,
    })
    return str(data.get("text") or "")


def session_id_for(chat_key: str) -> str:
    try:
        scopes = json.loads((DSH_HOME / "session-scopes.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    for key, value in scopes.items():
        scope = str(value.get("scope") or value.get("chat") or "") if isinstance(value, dict) else str(value or "")
        if scope == chat_key:
            return str(key)
    return ""


async def l0_recent(chat_key: str, limit: int = 80) -> str:
    sid = session_id_for(chat_key)
    if not sid:
        return ""
    data = await cmem_call("POST", "/context", {
        "tiers": {"L0": max(1, int(limit))},
        "session_id": sid,
        "purpose": "recent",
        "max_chars": 16000,
    })
    return str(data.get("text") or "")


async def recent_dialogue(limit: int = 80) -> str:
    return await l0_recent(OWNER_CHAT_KEY, limit)


async def context_evidence(body: dict) -> dict:
    return await cmem_call("POST", "/context/evidence", body)


async def ingest(text: str, tier: str = "L0", tags: list[str] | None = None) -> int | None:
    data = await cmem_call("POST", "/ingest", {
        "text": text,
        "tier": tier,
        "subject": "self",
        "tags": tags or ["raw"],
        "embed": False,
    })
    mid = data.get("id")
    return int(mid) if mid is not None else None


async def set_emotion(label: str, valence: float, arousal: float, reason: str = "", source: str = "self-check") -> None:
    await cmem_call("POST", "/state", {"valence": valence, "arousal": arousal})
    await cmem_call("POST", "/emotion", {
        "label": label,
        "valence": valence,
        "arousal": arousal,
        "trigger": reason,
        "source": source,
    })
