"""DSH hook 端点：召回与写入策略放在服务端。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from memory.context import build_context
from memory_core import MemoryInput
from persona.context import build_persona_context

_DATA_DIR = Path(os.environ.get("CMEM_DATA_DIR") or ".")
HOOK_LOG = Path(os.environ.get("CMEM_HOOK_LOG") or (_DATA_DIR.parent / "hook-events.jsonl"))


def _log(event: dict) -> None:
    try:
        HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HOOK_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": int(time.time()), **event}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _query(messages) -> str:
    texts: list[str] = []
    for item in messages or []:
        if isinstance(item, dict):
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
        else:
            role = ""
            content = str(item or "").strip()
        if role in ("user", "assistant") and content:
            texts.append(content)
    return "\n".join(texts[-4:])[-1000:]


def pre_step(store, embedder, body: dict) -> dict:
    system = build_persona_context(store.get_persona()).get("text", "")
    query = _query(body.get("messages"))
    recall = ""
    if query:
        ctx = build_context(store, {
            "query": query,
            "tiers": ["L1", "L3"],
            "limits": {"L1": 25, "L3": 15},
            "scope": body.get("scope") or "",
            "purpose": "recall",
            "max_chars": 6000,
        }, embedder)
        recall = str(ctx.get("text") or "")
    _log({
        "event": "pre_step",
        "request_id": body.get("request_id") or "",
        "session": body.get("session") or "",
        "scope": body.get("scope") or "",
        "system_chars": len(system),
        "recall_chars": len(recall),
    })
    return {"ok": True, "system": system, "recall": recall}


def _ids(value) -> list[int]:
    if isinstance(value, list):
        return [int(x) for x in value if str(x).strip().isdigit()]
    try:
        data = json.loads(value or "[]")
        return [int(x) for x in data] if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def evidence(store, body: dict) -> dict:
    """最近 L1/L3 + 它们引用的 L0 证据（按 id/文本去重）。

    body 里带 ids 时改成「按 id 精确取」：人格条目挂着 {{L3:123}}，
    复盘要把它展开成「标题 · 状态 + 正文 + 当时的话」。
    """
    want_ids = [int(x) for x in (body.get("ids") or []) if str(x).strip().isdigit()]
    tiers = [str(t).upper() for t in (body.get("tiers") or ["L1", "L3"])]
    limits = body.get("limits") or {"L1": 15, "L3": 10}
    if want_ids:
        limits = {t: max(int(limits.get(t, 10)), len(want_ids)) for t in limits}
    scope = str(body.get("scope") or "")
    l0_limit = max(1, min(300, int(body.get("l0_limit") or 50)))
    items: list[dict] = []
    l1_ids: set[int] = set()
    l3_rows: list = []

    def fetch(tier: str) -> list:
        if want_ids:
            marks = ",".join("?" for _ in want_ids)
            rows = store.conn.execute(
                f"SELECT id,tier,text,ts,source_ids,scope FROM memory "
                f"WHERE tier=? AND id IN ({marks}) ORDER BY ts DESC",
                [tier, *want_ids],
            ).fetchall()
            return list(rows)
        limit = max(1, min(50, int(limits.get(tier, 10))))
        sql = "SELECT id,tier,text,ts,source_ids,scope FROM memory WHERE tier=?"
        args: list = [tier]
        if scope:
            sql += " AND (scope=? OR scope='global')"
            args.append(scope)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return store.conn.execute(sql, args).fetchall()

    for tier in tiers:
        for row in fetch(tier):
            item = {
                "id": int(row["id"]),
                "tier": str(row["tier"]),
                "text": str(row["text"]),
                "ts": float(row["ts"] or 0),
                "source_ids": _ids(row["source_ids"]),
            }
            items.append(item)
            if tier == "L1":
                l1_ids.add(item["id"])
            elif tier == "L3":
                l3_rows.append(item)

    # L3 的 source_ids 可能直接是 L0，也可能指向 L1；两种都处理
    src_ids = {sid for item in l3_rows for sid in item["source_ids"]}
    l0_ids: set[int] = set()
    if src_ids:
        marks = ",".join("?" for _ in src_ids)
        for row in store.conn.execute(
            f"SELECT id,tier FROM memory WHERE id IN ({marks})",
            list(src_ids),
        ):
            if str(row["tier"]) == "L0":
                l0_ids.add(int(row["id"]))
            elif str(row["tier"]) == "L1":
                l1_ids.add(int(row["id"]))

    if l1_ids:
        marks = ",".join("?" for _ in l1_ids)
        for row in store.conn.execute(
            f"SELECT source_ids FROM memory WHERE id IN ({marks})",
            list(l1_ids),
        ):
            l0_ids.update(_ids(row["source_ids"]))

    l0 = []
    if l0_ids:
        marks = ",".join("?" for _ in l0_ids)
        rows = store.conn.execute(
            f"SELECT id,text,ts,scope FROM memory WHERE tier='L0' AND id IN ({marks})",
            list(l0_ids),
        ).fetchall()
        seen_ids: set[int] = set()
        seen_text: set[str] = set()
        for row in rows:
            mid = int(row["id"])
            text = str(row["text"] or "").strip()
            if mid in seen_ids or not text:
                continue
            digest = text[:200]
            if digest in seen_text:
                continue
            seen_ids.add(mid)
            seen_text.add(digest)
            l0.append({"id": mid, "text": text, "ts": float(row["ts"] or 0)})

    l0.sort(key=lambda x: x["ts"])
    return {"ok": True, "items": items, "l0": l0[:l0_limit], "l0_total": len(l0_ids)}


def turn_end(store, lock, gate, embedder, body: dict) -> dict:
    user = str(body.get("user") or "").strip()
    assistant = str(body.get("assistant") or "").strip()
    if not user or len(user) < 2:
        _log({"event": "turn_end", "session": body.get("session") or "", "scope": body.get("scope") or "", "stored": False, "reason": "empty"})
        return {"ok": True, "stored": False, "reason": "empty"}
    context = str(body.get("context") or "")
    result = gate.score(user, context)
    if not result.get("store"):
        _log({
            "event": "turn_end",
            "session": body.get("session") or "",
            "scope": body.get("scope") or "",
            "stored": False,
            "reason": result.get("reason"),
            "surprisal": result.get("score"),
        })
        return {"ok": True, "stored": False, "surprisal": result.get("score"), "reason": result.get("reason")}
    merged = "\n".join(part for part in (f"主人：{user}", f"我：{assistant}" if assistant else "") if part)
    extra_tags = body.get("tags") if isinstance(body.get("tags"), list) else []
    tags = ["raw", f"session:{body.get('session') or ''}"]
    for tag in extra_tags[:20]:
        value = str(tag or "").strip()
        if value.startswith("sticker:") and value.split(":", 1)[1] in {"inbox", "cache", "tmp"}:
            continue
        if value and len(value) <= 180 and value not in tags:
            tags.append(value)
    vec = None
    vec_model = None
    if embedder.enabled:
        vec = embedder.embed_one(merged)
        vec_model = embedder.model if vec else None
    with lock:
        mid = store.add(MemoryInput(
            text=merged,
            tier="L0",
            subject="self",
            tags=tags,
            vec=vec,
            vec_model=vec_model,
            user_id=str(body.get("user_id") or ""),
            scope=str(body.get("scope") or "global"),
            nickname=str(body.get("nickname") or ""),
        ))
    _log({
        "event": "turn_end",
        "session": body.get("session") or "",
        "scope": body.get("scope") or "",
        "stored": True,
        "id": mid,
        "surprisal": result.get("score"),
    })
    return {"ok": True, "stored": True, "id": mid, "surprisal": result.get("score")}
