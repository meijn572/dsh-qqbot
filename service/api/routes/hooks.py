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
            "tiers": ["L1", "L2", "L3", "L4"],
            "limits": {"L1": 20, "L2": 4, "L3": 10, "L4": 4},
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
            tags=["raw", f"session:{body.get('session') or ''}"],
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
