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


async def diary_recent(days: int = 7) -> list[dict]:
    """中间层：最近几天的日记（含 text / changes / open_questions）。"""
    data = await cmem_call("GET", "/diary")
    rows = data if isinstance(data, list) else (data.get("items") or [])
    rows = [r for r in rows if isinstance(r, dict)]
    return rows[:max(1, int(days))][::-1]


def format_diary(rows: list[dict]) -> str:
    """把中间层渲染成给复盘看的文本；没内容返回空串。

    渲染规则在服务端 render.py，这里优先用 it['line']，
    拿不到才退回自己拼（兼容旧数据）。
    """
    blocks = []
    for r in rows or []:
        line = str(r.get("line") or "").strip()
        if line:
            blocks.append(line)
            continue
        parts = []
        text = str(r.get("text") or "").strip()
        if text:
            parts.append(text)
        for key, title in (("changes", "变化"), ("open_questions", "还没想清"),
                           ("relationship", "那天的关系")):
            body = str(r.get(key) or "").strip()
            if body:
                parts.append(f"{title}：\n{body}")
        if parts:
            blocks.append(f"【{r.get('date')}】\n" + "\n".join(parts))
    return "\n\n".join(blocks)


async def input_block(name: str, **body) -> dict:
    """取一份输入配方：POST /input/<name>。

    返回 {"text": 拼好的整块, "blocks": {名字: 内容}}。
    消费方自己挑块，不再各自拼素材。
    """
    data = await cmem_call("POST", f"/input/{name}", body)
    if not isinstance(data, dict) or not data.get("ok"):
        return {"text": "", "blocks": {}}
    return {"text": str(data.get("text") or ""),
            "blocks": data.get("blocks") or {}}


async def persona_context() -> str:
    """人格文本（不含溯源标记）：直接取 /persona 渲染好的 text。"""
    data = await cmem_call("GET", "/persona")
    return str(data.get("text") or "")


async def long_term_memory(tiers: dict | None = None) -> str:
    if tiers and isinstance(tiers, dict):
        body = {"limits": {str(k).upper(): int(v) for k, v in tiers.items()}}
    else:
        body = {"limits": {"L1": 80, "L3": 40}}
    data = await input_block("evidence", **body)
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
    data = await input_block("recent", session_id=sid, limit=max(1, int(limit)))
    return str(data.get("text") or "")


async def recent_batches(chat_key: str, batches: int = 2, idle_seconds: int = 300,
                         max_chars: int = 8000) -> str:
    """按空闲间隔切好的最近几段对话；会话重建后接着聊用。

    不按会话 id 过滤 —— 重建后新会话里没有旧消息，得从记忆里捞。
    """
    data = await input_block("batches", scope=chat_key,
                             batches=max(1, int(batches)),
                             idle_seconds=max(60, int(idle_seconds)),
                             max_chars=max_chars)
    return str(data.get("text") or "")


async def recent_dialogue(limit: int = 80) -> str:
    return await l0_recent(OWNER_CHAT_KEY, limit)


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


