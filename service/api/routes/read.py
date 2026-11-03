"""只读路由：简单查询直接返回 payload。"""
from __future__ import annotations


def simple_get(path: str, query: dict, store):
    if path == "/stats":
        return {"ok": True, "stats": store.stats()}
    if path == "/activity":
        date = (query.get("date") or [None])[0] or None
        return store.list_activities(date)
    if path == "/emotion":
        days = int((query.get("days") or ["0"])[0])
        limit = int((query.get("limit") or ["50"])[0])
        return store.emotion_log_list(limit=limit, days=days)
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
