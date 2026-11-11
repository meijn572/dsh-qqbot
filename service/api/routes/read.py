"""只读路由：简单查询直接返回 payload。"""
from __future__ import annotations

import time


def simple_get(path: str, query: dict, store):
    if path == "/stats":
        return {"ok": True, "stats": store.stats()}
    if path == "/activity":
        unshared = str((query.get("unshared") or ["0"])[0]).lower() in ("1", "true", "yes")
        if unshared:
            kind = str((query.get("kind") or ["bili"])[0])
            limit = int((query.get("limit") or ["5"])[0])
            return store.unshared_activities(kind=kind, limit=limit)
        date = (query.get("date") or [None])[0] or None
        kind = str((query.get("kind") or [""])[0])
        limit = int((query.get("limit") or ["100"])[0])
        return store.list_activities(date, limit=limit, kind=kind)
    if path == "/bili/insights":
        kind = str((query.get("kind") or [""])[0])
        limit = int((query.get("limit") or ["20"])[0])
        days = int((query.get("days") or ["90"])[0])
        return store.bili_insights(kind=kind, limit=limit, days=days)
    if path == "/emotion":
        # 情绪已并入 L1：这里读带情绪的 L1，接口形状保持不变
        days = int((query.get("days") or ["0"])[0])
        limit = int((query.get("limit") or ["50"])[0])
        sql = ("SELECT id,ts,emotion_label,emotion_valence,emotion_arousal,text "
               "FROM memory WHERE tier='L1' AND emotion_label!=''")
        args: list = []
        if days > 0:
            sql += " AND ts>=?"
            args.append(time.time() - days * 86400)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        rows = store.conn.execute(sql, args).fetchall()
        return [{
            "id": int(r["id"]), "ts": float(r["ts"] or 0),
            "label": str(r["emotion_label"] or ""),
            "valence": float(r["emotion_valence"] or 0),
            "arousal": float(r["emotion_arousal"] or 0),
            "trigger": str(r["text"] or ""),
            "source": "L1",
        } for r in rows]
    if path == "/persona/user":
        return {"user_profile": store.get_user_profile()}
    if path == "/memories":
        tier = (query.get("tier") or ["all"])[0]
        q = (query.get("q") or [""])[0]
        limit = int((query.get("limit") or ["100"])[0])
        offset = int((query.get("offset") or ["0"])[0])
        return store.list_memories(tier=tier, q=q, limit=limit, offset=offset)
    if path == "/browse":
        return store.browsed_list()
    if path == "/tasks":
        return store.task_list()
    if path == "/notes":
        return store.note_list()
    if path == "/outbound":
        scope = str((query.get("scope") or [""])[0])
        limit = int((query.get("limit") or ["5"])[0])
        return store.outbound_recent(scope=scope, limit=limit)
    if path == "/diary":
        return store.diary_list()
    return None
