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


async def expand_persona_links(constitution: str) -> str:
    """把人格里的 {{L3:123}} 展开成「标题 · 状态 + 正文」，给复盘看。

    日常注入走 persona.mjs，那边是直接抹掉的——模型不需要知道来处。
    复盘要判断这条还成不成立，才需要看见当时发生了什么。
    """
    import re as _re
    text = str(constitution or "")
    ids = sorted({int(x) for x in _re.findall(r"\{\{L3:(\d+)\}\}", text)})
    if not ids:
        return text
    info: dict[int, dict] = {}
    for tier in ("L3", "L4"):
        try:
            data = await cmem_call("GET", f"/memories?tier={tier}&limit=200")
            for item in (data.get("items") or []):
                try:
                    mid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                if mid in ids:
                    info[mid] = item
        except Exception:  # noqa: BLE001
            continue
    for mid in ids:
        item = info.get(mid)
        if not item:
            text = text.replace("{{L3:%d}}" % mid, "")
            continue
        title = str(item.get("thread_title") or "").strip() or "（无标题）"
        status = str(item.get("thread_status") or "").strip() or "?"
        body = str(item.get("summary") or item.get("text") or "").strip().replace("\n", " ")[:200]
        rendered = f"〔{title} · {status}〕{body}"
        text = text.replace("{{L3:%d}}" % mid, rendered)
    return text


async def diary_recent(days: int = 7) -> list[dict]:
    """中间层：最近几天的日记（含 text / changes / open_questions）。"""
    data = await cmem_call("GET", "/diary")
    rows = data if isinstance(data, list) else (data.get("items") or [])
    rows = [r for r in rows if isinstance(r, dict)]
    return rows[:max(1, int(days))][::-1]


def format_diary(rows: list[dict]) -> str:
    """把中间层渲染成给复盘看的文本；没内容返回空串。"""
    blocks = []
    for r in rows:
        parts = []
        text = str(r.get("text") or "").strip()
        if text:
            parts.append(text)
        changes = str(r.get("changes") or "").strip()
        if changes:
            parts.append("变化：\n" + changes)
        questions = str(r.get("open_questions") or "").strip()
        if questions:
            parts.append("还没想清：\n" + questions)
        if parts:
            blocks.append(f"【{r.get('date')}】\n" + "\n".join(parts))
    return "\n\n".join(blocks)


async def persona_context() -> str:
    data = await cmem_call("GET", "/persona/context")
    return str(data.get("text") or "")


async def long_term_memory(tiers: dict | None = None) -> str:
    data = await cmem_call("POST", "/context", {
        "tiers": tiers or {"L1": 80, "L3": 40},
        "purpose": "review",
        "max_chars": 16000,
    })
    return str(data.get("text") or "")


async def bili_insights(kind: str = "", limit: int = 20, days: int = 90) -> list[dict]:
    """B 站视频留下的 L3 感悟，按 self/style/relation 过滤。"""
    data = await cmem_call(
        "GET", f"/bili/insights?kind={kind}&limit={int(limit)}&days={int(days)}"
    )
    return data if isinstance(data, list) else []


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


async def set_emotion(label: str, valence: float, arousal: float, reason: str = "", source: str = "self-check",
                      ts_start: float | None = None, ts_end: float | None = None) -> None:
    await cmem_call("POST", "/state", {"valence": valence, "arousal": arousal})
    body = {
        "label": label,
        "valence": valence,
        "arousal": arousal,
        "trigger": reason,
        "source": source,
    }
    if ts_start is not None:
        body["ts_start"] = float(ts_start)
    if ts_end is not None:
        body["ts_end"] = float(ts_end)
    await cmem_call("POST", "/emotion", body)
