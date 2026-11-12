"""统一记忆块格式：分层、配额、scope、人称提示。"""
from __future__ import annotations

import time


def build_context(store, body: dict, embedder) -> dict:
    tiers = body.get("tiers")
    limits: dict[str, int] = {}
    if isinstance(tiers, dict):
        raw = tiers
        tiers = [str(k).upper() for k in raw.keys()]
        limits = {str(k).upper(): int(v) for k, v in raw.items()}
    elif isinstance(tiers, list):
        tiers = [str(t).upper() for t in tiers]
        each = max(1, int(body.get("limit") or 40))
        limits = {t: each for t in tiers}
    else:
        tiers = ["L1", "L3"]
        limits = {"L1": 80, "L3": 40}
    if isinstance(body.get("limits"), dict):
        limits.update({str(k).upper(): int(v) for k, v in body["limits"].items()})
    tiers = [t for t in tiers if t in {"L0", "L1", "L2", "L3", "L4"}]
    max_chars = max(500, min(30000, int(body.get("max_chars") or 16000)))
    scope = str(body.get("scope") or "")
    session_id = str(body.get("session_id") or "")
    purpose = str(body.get("purpose") or "review")
    query = str(body.get("query") or "").strip()
    focus = str(body.get("focus") or "").strip()
    items = []
    if query or focus:
        qvec = None
        if embedder.enabled and body.get("embed_query", True):
            qvec = embedder.embed_one(query or focus)
        hits = store.search(
            query=query,
            query_vec=qvec,
            top_k=max(1, min(40, int(body.get("top_k") or sum(limits.values()) or 8))),
            tiers=tiers,
            subject=body.get("subject"),
            focus=focus or None,
            scopes=body.get("scopes") or ([scope, "global"] if scope else None),
            before_ts=body.get("before_ts"),
        )
        # 严格按层配额截断，避免 L1 命中过多把 L3 挤掉
        taken: dict[str, int] = {}
        items = []
        for hit in hits:
            tier = str(hit.tier)
            cap = max(1, int(limits.get(tier, 10)))
            if taken.get(tier, 0) >= cap:
                continue
            taken[tier] = taken.get(tier, 0) + 1
            items.append({"id": hit.id, "tier": tier, "text": hit.text, "ts": hit.ts})
    else:
        for tier in tiers:
            limit = max(1, min(200, int(limits.get(tier, 10))))
            if tier == "L0" and session_id:
                # 排除自主刷写的 L0（tags 带 bili）：那些不该出现在对话上下文里
                rows = store.conn.execute(
                    "SELECT id,text,ts FROM memory WHERE tier='L0' AND tags LIKE ? "
                    "AND tags NOT LIKE '%\"bili\"%' ORDER BY ts DESC LIMIT ?",
                    (f"%session:{session_id}%", limit),
                ).fetchall()
            elif scope and tier != "L0":
                rows = store.conn.execute(
                    "SELECT id,text,ts FROM memory WHERE tier=? AND (scope=? OR scope='global') ORDER BY ts DESC LIMIT ?",
                    (tier, scope, limit),
                ).fetchall()
            elif scope:
                rows = store.conn.execute(
                    "SELECT id,text,ts FROM memory WHERE tier=? AND scope=? ORDER BY ts DESC LIMIT ?",
                    (tier, scope, limit),
                ).fetchall()
            else:
                rows = store.conn.execute(
                    "SELECT id,text,ts FROM memory WHERE tier=? ORDER BY ts DESC LIMIT ?",
                    (tier, limit),
                ).fetchall()
            items.extend({"id": int(r["id"]), "tier": tier, "text": str(r["text"]), "ts": r["ts"]} for r in rows)
    if not items:
        return {"ok": True, "text": "", "count": 0, "counts": {}}
    # L3 在前：它是事件级，比 L1 的细节更该先被读到；
    # 6000 字截断是从尾部砍的，把 L1 放后面才不会被优先砍掉
    tier_rank = {"L3": 0, "L4": 0, "L2": 1, "L1": 2, "L0": 3}
    order = {t: tier_rank.get(t, 9) for t in tiers}
    if purpose == "recent":
        items.sort(key=lambda x: float(x["ts"] or 0))
    else:
        items.sort(key=lambda x: (order.get(x["tier"], 99), -float(x["ts"] or 0)))
    lines = []
    counts: dict[str, int] = {}
    recalled_ids: list[int] = []
    for item in items:
        tier = str(item["tier"])
        text = str(item["text"]).strip()
        if not text:
            continue
        counts[tier] = counts.get(tier, 0) + 1
        if tier in ("L1", "L2", "L3") and item.get("id"):
            recalled_ids.append(int(item["id"]))
        label = {"L0": "原话", "L1": "上次聊到的", "L2": "我的判断", "L3": "记得的事", "L4": "核心记忆"}.get(tier, tier)
        if tier in ("L0", "L3"):
            stamp = time.strftime("%m-%d %H:%M", time.localtime(float(item["ts"] or 0)))
            lines.append(f"[{label} · {stamp}] {text}")
        else:
            lines.append(f"[{label}] {text}")
    if recalled_ids:
        try:
            store.note_recall(recalled_ids)
        except Exception:
            pass
    header = (
        "以下是最近的对话原话（按时间从早到晚）："
        if purpose == "recent"
        else "以下是你记得的事（不是刚听到的话）。\n"
             "用第一人称理解；主人就是主人，不要把他/她的事说成你自己的。"
    )
    text = header + "\n" + "\n".join(lines)
    return {"ok": True, "text": text[:max_chars], "count": len(lines), "counts": counts}
