"""记忆路由逻辑：写入、检索、遗忘。"""
from __future__ import annotations

from memory_core import MemoryInput


def ingest(store, lock, embedder, body: dict) -> dict:
    text = (body.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    tier = str(body.get("tier") or "L1")
    subject = str(body.get("subject") or "self")
    vec = None
    vec_model = None
    if body.get("embed", True) and embedder.enabled:
        vec = embedder.embed_one(text)
        vec_model = embedder.model if vec else None
    with lock:
        mid = store.add(MemoryInput(
            text=text,
            tier=tier,
            subject=subject,
            summary=body.get("summary"),
            source_ids=body.get("source_ids"),
            tags=body.get("tags"),
            ts=body.get("ts"),
            half_life_days=body.get("half_life_days"),
            vec=vec,
            vec_model=vec_model,
            user_id=str(body.get("user_id") or ""),
            scope=str(body.get("scope") or "global"),
            nickname=str(body.get("nickname") or ""),
        ))
    return {
        "ok": True,
        "id": mid,
        "embedded": vec is not None,
        "embedding_error": None if vec or not embedder.enabled else embedder.last_error,
    }


def search(store, embedder, body: dict) -> dict:
    query = (body.get("query") or "").strip()
    focus = body.get("focus")
    if not query and not focus:
        raise ValueError("query or focus is required")
    qvec = None
    if embedder.enabled and body.get("embed_query", True):
        qvec = embedder.embed_one(query or focus or "")
    hits = store.search(
        query=query,
        query_vec=qvec,
        top_k=int(body.get("top_k") or 6),
        scopes=body.get("scopes") or None,
        tiers=body.get("tiers"),
        subject=body.get("subject"),
        min_fused=float(body.get("min_fused") or 0.30),
        focus=focus,
    )
    return {
        "ok": True,
        "query": query,
        "hits": [h.to_dict() for h in hits],
        "count": len(hits),
        "embedding_used": qvec is not None,
    }


def forget(store, lock, mem_id: int) -> dict:
    with lock:
        ok = store.forget(int(mem_id))
    return {"ok": ok, "id": int(mem_id)}
