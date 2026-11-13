"""取数原语：单层、原始行、去重排好序。**不渲染**。

取法就这么几种，都挂在同一层上：

    rows(store, "L1", ...)        最近 N 条 / 时间窗 / 按 id / 按标签 / 按状态
    search(store, "L3", query)    相关召回
    batches(store, "L0", ...)     按空闲切批

需要跨层就套一层：

    rows_each(store, ("L1", "L3"), ...)   同一种取法跑多层
    sources(store, rows)                  这些行引用了哪些来源（按 id 取回来）

返回一律是 dict 列表，已去重、已按时间排好。渲染交给 render.py，
配方只负责「选原语 → 给参数 → 调渲染」。
"""
from __future__ import annotations

import json
import time

from render import (render_batches, render_diary, render_diary_row,
                    render_evidence, render_l0_recent, render_memory_line,
                    render_persona, strip_persona_links)


# ---------------------------------------------------------------------------
# 单层取数
# ---------------------------------------------------------------------------

def _fetch(store, sql: str, args: list) -> list[dict]:
    try:
        return [dict(r) for r in store.conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: set = set()
    out: list[dict] = []
    for row in rows:
        mid = row.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        out.append(row)
    return out


def rows(store, tier: str, *, limit: int = 50, order: str = "desc",
         since: float | None = None, until: float | None = None,
         scope: str = "", session_id: str = "",
         tags: list[str] | None = None, exclude_tags: list[str] | None = None,
         statuses: list[str] | None = None, ids: list[int] | None = None,
         include_stale: bool = True) -> list[dict]:
    """某一层按条件取行。最近 N 条 / 时间窗 / 按 id / 按标签 / 按状态都走这里。"""
    sql = ["SELECT * FROM memory WHERE tier=?"]
    args: list = [str(tier or "").upper()]

    if ids is not None:
        want = [int(x) for x in ids if str(x).strip().lstrip("-").isdigit()]
        if not want:
            return []
        sql.append(f"AND id IN ({','.join('?' for _ in want)})")
        args.extend(want)

    if session_id:
        sql.append("AND tags LIKE ?")
        args.append(f"%session:{session_id}%")
    elif scope:
        sql.append("AND (scope=? OR scope='global')")
        args.append(scope)

    if since is not None:
        sql.append("AND ts>=?")
        args.append(float(since))
    if until is not None:
        sql.append("AND ts<?")
        args.append(float(until))

    for tag in tags or []:
        sql.append("AND tags LIKE ?")
        args.append(f"%{tag}%")
    for tag in exclude_tags or []:
        sql.append("AND tags NOT LIKE ?")
        args.append(f"%{tag}%")

    if statuses:
        marks = ",".join("?" for _ in statuses)
        sql.append(f"AND thread_status IN ({marks})")
        args.extend(list(statuses))

    if not include_stale:
        sql.append("AND stale_at IS NULL")

    sql.append("ORDER BY ts " + ("ASC" if str(order).lower() == "asc" else "DESC"))
    sql.append("LIMIT ?")
    args.append(max(1, int(limit)))
    return _dedupe(_fetch(store, " ".join(sql), args))


def rows_each(store, tiers, **kw) -> dict[str, list[dict]]:
    """同一种取法跑多层，每层各自套自己的上限。

    limits 用 {"L1": 50, "L3": 30}；不传就都用 limit。
    """
    limits = kw.pop("limits", None) or {}
    out: dict[str, list[dict]] = {}
    for tier in tiers:
        body = dict(kw)
        body["limit"] = int(limits.get(tier, kw.get("limit", 50)))
        out[str(tier).upper()] = rows(store, tier, **body)
    return out


def search(store, tier: str, query: str, *, top_k: int = 6, scope: str = "",
           before_ts: float | None = None, embedder=None,
           min_fused: float = 0.3) -> list[dict]:
    """某一层里按 query 召回，返回带 score 的行。"""
    query = str(query or "").strip()
    if not query:
        return []
    qvec = None
    if embedder is not None and getattr(embedder, "enabled", False):
        try:
            qvec = embedder.embed_one(query)
        except Exception:  # noqa: BLE001
            qvec = None
    hits = store.search(
        query=query, query_vec=qvec, top_k=max(1, int(top_k)),
        tiers=[str(tier or "").upper()],
        scopes=[scope, "global"] if scope else None,
        before_ts=before_ts, min_fused=min_fused,
    )
    out: list[dict] = []
    for hit in hits or []:
        row = {"id": int(hit.id), "tier": str(hit.tier), "text": str(hit.text),
               "ts": float(hit.ts), "score": float(getattr(hit, "score", 0.0) or 0.0)}
        full = rows(store, row["tier"], ids=[row["id"]], limit=1)
        if full:
            full[0]["score"] = row["score"]
            out.append(full[0])
    return _dedupe(out)


def batches(store, tier: str, *, idle_seconds: float = 300, want: int = 2,
            **kw) -> list[list[dict]]:
    """按空闲间隔把某一层的行切成批，取最近 want 批（旧的在前）。"""
    flat = rows(store, tier, **kw)
    out: list[list[dict]] = []
    cur: list[dict] = []
    prev = None
    for row in flat:
        ts = float(row.get("ts") or 0)
        if prev is not None and prev - ts > max(60.0, float(idle_seconds)):
            if cur:
                out.append(cur)
            cur = []
            if len(out) >= max(1, int(want)):
                break
        cur.append(row)
        prev = ts
    if cur and len(out) < max(1, int(want)):
        out.append(cur)
    return list(reversed(out))


def sources(store, items, *, limit: int = 60) -> list[dict]:
    """这些行引用了哪些来源。给 L3 就能取回它的 L1/L0。

    其实就是「按一批 id 取」，跨层。
    """
    ids: set[int] = set()
    for item in items or []:
        try:
            ids.update(int(x) for x in json.loads(item.get("source_ids") or "[]"))
        except Exception:  # noqa: BLE001
            continue
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    found = _fetch(store,
                   f"SELECT * FROM memory WHERE id IN ({marks}) ORDER BY ts ASC LIMIT ?",
                   [*ids, max(1, int(limit))])
    return _dedupe(found)


def diary_days(store, *, days: int = 7, before_date: str | None = None) -> list[dict]:
    """最近几天的日记，旧的在前。"""
    fetched = store.diary_list(max(1, int(days)) + 3)
    rows_out = [r for r in fetched if str(r.get("date") or "")]
    if before_date:
        rows_out = [r for r in rows_out if str(r.get("date")) < str(before_date)]
    return list(reversed(rows_out[:max(1, int(days))]))


# ---------------------------------------------------------------------------
# 人格
# ---------------------------------------------------------------------------

def persona_raw(store) -> tuple[str, str]:
    data = store.get_persona()
    return str(data.get("constitution") or ""), str(data.get("user_profile") or "")


def expand_persona_links(store, constitution: str) -> str:
    """把 【L3:123】 展开成「标题 · 状态 + 正文 + 当时的话」，给复盘看。"""
    import re as _re

    text = str(constitution or "")
    ids = sorted({int(x) for x in _re.findall(r"【L3:(\d+)】", text)})
    if not ids:
        return text

    found = _fetch(store,
                   f"SELECT * FROM memory WHERE tier IN ('L3','L4') "
                   f"AND id IN ({','.join('?' for _ in ids)})", list(ids))
    info = {int(r["id"]): r for r in found}
    quotes: dict[int, list[str]] = {}
    for src in sources(store, found):
        for mid, row in info.items():
            try:
                mine = [int(x) for x in json.loads(row.get("source_ids") or "[]")]
            except Exception:  # noqa: BLE001
                continue
            if int(src["id"]) in mine:
                quotes.setdefault(mid, []).append(str(src.get("text") or "")[:200])

    for mid in ids:
        token = f"【L3:{mid}】"
        row = info.get(mid)
        if row is None:
            text = text.replace(" " + token, "").replace(token, "")
            continue
        title = str(row.get("thread_title") or "").strip() or "（无标题）"
        status = str(row.get("thread_status") or "").strip() or "?"
        body = str(row.get("summary") or row.get("text") or "").strip().replace("\n", " ")[:200]
        lines = [f"〔{title} · {status}〕{body}"]
        got = quotes.get(mid) or []
        if got:
            lines.append("当时的话：" + " / ".join(got[:3]))
        text = text.replace(token, "\n    ".join(lines))
    return text


def persona_block(store, *, expand: bool = False) -> dict[str, str]:
    """人格三个视图：原文、拼接好的文本、展开来源的版本。"""
    constitution, profile = persona_raw(store)
    expanded = expand_persona_links(store, constitution) if expand else constitution
    return {
        "constitution": expanded,
        "profile": profile,
        "persona": render_persona(
            strip_persona_links(expanded) if not expand else expanded, profile),
    }


# ---------------------------------------------------------------------------
# 配方
# ---------------------------------------------------------------------------

# 每个用途取多少、要不要带原话、证据块最多多少字
DEFAULT_LIMITS = {
    "evidence":  {"L1": 15, "L3": 10, "recent": 0,
                  "quotes": False, "max_chars": 8000},
    "diary":     {"L1": 40, "L3": 5, "recent": 0,
                  "quotes": False, "max_chars": 8000},
    # 5 天一次、看全窗口，所以给得比别的大
    "review":    {"L1": 300, "L3": 200, "recent": 30,
                  "quotes": False, "max_chars": 24000},
    # 调口吻要真实措辞，只有它带原话
    "style":     {"L1": 30, "L3": 20, "recent": 60,
                  "quotes": True, "max_chars": 12000},
    "profile":   {"L1": 90, "L3": 50, "recent": 20,
                  "quotes": False, "max_chars": 18000},
    "important": {"L1": 30, "L3": 20, "recent": 80,
                  "quotes": False, "max_chars": 10000},
}


def _limits(name: str, body: dict) -> dict:
    """默认值表 + 调用方覆盖。数字键是条数，其它键（quotes/max_chars）原样保留。"""
    merged = dict(DEFAULT_LIMITS.get(name) or {})
    given = body.get("limits")
    if isinstance(given, dict):
        for k, v in given.items():
            key = str(k)
            if key in ("quotes",):
                merged[key] = bool(v)
            elif key == "max_chars":
                merged[key] = int(v)
            else:
                merged[key.upper() if len(key) <= 2 else key] = int(v)
    for key in ("quotes", "max_chars"):
        if key in body and key not in (given or {}):
            merged[key] = body[key]
    return merged


def _evidence_blocks(store, body: dict, limits: dict) -> tuple[str, list[str]]:
    """L1/L3 各取一批，按需带上它们引用的原话。返回（渲染文本, refs）。"""
    tiers = [t for t in ("L1", "L3") if limits.get(t)]
    picked = rows_each(store, tiers, limits=limits,
                       scope=str(body.get("scope") or ""),
                       since=body.get("since") or None,
                       until=body.get("until") or None)
    items: list[dict] = []
    for tier in ("L3", "L1"):
        items.extend(picked.get(tier) or [])
    quotes = bool(limits.get("quotes"))
    sources_rows = (sources(store, picked.get("L3") or [],
                            limit=int(limits.get("L0") or 50)) if quotes else [])
    refs = [f"{r['tier']}:{r['id']}" for r in items][:8]
    refs += [f"L0:{r['id']}" for r in sources_rows][:4]
    return render_evidence(items, sources_rows or None,
                           max_chars=int(limits.get("max_chars") or 16000)), refs[:8]


def recipe_evidence(store, body: dict, embedder=None) -> dict:
    text, refs = _evidence_blocks(store, body, _limits("evidence", body))
    return {"ok": True, "blocks": {"evidence": text, "memories": text},
            "text": text, "refs": refs}


def _persona_with_evidence(store, body: dict, name: str, *, expand: bool) -> dict:
    limits = _limits(name, body)
    blocks = persona_block(store, expand=expand)
    text, refs = _evidence_blocks(store, body, limits)
    blocks["evidence"] = text
    blocks["memories"] = text
    if limits.get("recent"):
        blocks["recent"] = render_l0_recent(rows(
            store, "L0", scope=str(body.get("scope") or ""),
            session_id=str(body.get("session_id") or ""),
            limit=int(limits["recent"]),
            exclude_tags=['"bili"']))
    return {"blocks": blocks, "refs": refs}


def _finish(payload: dict) -> dict:
    """拼 text 时按内容去重：constitution/profile 已经在 persona 里了。"""
    blocks = payload.get("blocks") or {}
    # persona 已经把 constitution/profile 包含进去了，拼正文时跳过这两块
    skip = {"constitution", "profile"} if blocks.get("persona") else set()
    seen: set[str] = set()
    parts: list[str] = []
    for key, value in blocks.items():
        if key in skip:
            continue
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return {"ok": True, "blocks": blocks, "refs": payload.get("refs") or [],
            "text": "\n\n".join(parts)}


def recipe_review(store, body: dict, embedder=None) -> dict:
    payload = _persona_with_evidence(store, body, "review", expand=True)
    payload["blocks"]["diary"] = render_diary(
        diary_days(store, days=int(body.get("diary_days") or 7)))
    return _finish(payload)


def recipe_style(store, body: dict, embedder=None) -> dict:
    payload = _persona_with_evidence(store, body, "style", expand=False)
    payload["blocks"]["material"] = payload["blocks"].get("evidence", "")
    return _finish(payload)


def recipe_profile(store, body: dict, embedder=None) -> dict:
    return _finish(_persona_with_evidence(store, body, "profile", expand=False))


def recipe_important(store, body: dict, embedder=None) -> dict:
    return _finish(_persona_with_evidence(store, body, "important", expand=False))


def recipe_diary(store, body: dict, embedder=None) -> dict:
    """昨天的日记素材：人格 + 昨天的便签 + 相关的旧事 + 前几天的日记。"""
    import datetime as _dt

    day = None
    target = str(body.get("date") or "").strip()
    if target:
        try:
            day = _dt.date.fromisoformat(target)
        except ValueError:
            day = None
    if day is None:
        day = _dt.date.today() - _dt.timedelta(days=1)
    start = _dt.datetime.combine(day, _dt.time.min).timestamp()
    end = start + 86400
    limits = _limits("diary", body)
    scope = str(body.get("scope") or "")

    blocks = persona_block(store, expand=False)

    # 昨天记下的便签：情绪只做附注
    notes = rows(store, "L1", since=start, until=end, scope=scope, order="asc",
                 limit=int(limits.get("L1") or 40))
    lines = []
    for row in notes:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        label = str(row.get("emotion_label") or "").strip()
        lines.append(f"- （{label}）{text}" if label else f"- {text}")
    blocks["notes"] = "\n".join(lines)

    # 相关旧事：拿昨天最后几条便签去召回，再取它们的来源
    query = " ".join(str(r.get("text") or "") for r in notes[-5:])[:400]
    hits = search(store, "L3", query, top_k=int(limits.get("L3") or 5),
                  scope=scope, before_ts=start, embedder=embedder)
    lines = [render_memory_line(h) for h in hits[:int(limits.get("L3") or 5)]]
    blocks["memories"] = "\n".join(x for x in lines if x)

    blocks["prev_diary"] = render_diary(
        diary_days(store, days=int(body.get("diary_days") or 7),
                   before_date=day.isoformat()))

    text = "\n\n".join(v for v in blocks.values() if v)
    return {"ok": True, "date": day.isoformat(), "blocks": blocks, "text": text}


def recipe_recall(store, body: dict, embedder=None) -> dict:
    """对话/主动说用的召回：多层各取一批，按层分组渲染。"""
    query = str(body.get("query") or "").strip()
    limits = body.get("limits") or {"L1": 25, "L3": 15}
    scope = str(body.get("scope") or "")
    max_chars = int(body.get("max_chars") or 6000)
    tiers = [str(t).upper() for t in (body.get("tiers") or list(limits))]
    if not query:
        return {"ok": True, "blocks": {"recall": ""}, "text": "", "count": 0}

    picked = {t: search(store, t, query, top_k=int(limits.get(t, 10)),
                        scope=scope, embedder=embedder) for t in tiers}
    lines: list[str] = []
    for tier in sorted(tiers, key=lambda t: {"L3": 0, "L4": 0, "L2": 1,
                                             "L1": 2, "L0": 3}.get(t, 9)):
        for row in picked.get(tier) or []:
            line = render_memory_line(row)
            if line:
                lines.append(line)
    header = "以下是你记得的事（不是刚听到的话）。\n用第一人称理解；主人就是主人，不要把他/她的事说成你自己的。"
    text = (header + "\n" + "\n".join(lines))[:max_chars] if lines else ""
    return {"ok": True, "blocks": {"recall": text}, "text": text, "count": len(lines)}


def recipe_recent(store, body: dict, embedder=None) -> dict:
    session_id = str(body.get("session_id") or "")
    scope = str(body.get("scope") or "")
    if not session_id and not scope:
        return {"ok": True, "blocks": {"recent": ""}, "text": ""}
    got = rows(store, "L0", session_id=session_id, scope=scope,
               since=float(body.get("since") or 0) or None,
               limit=int(body.get("limit") or 80), exclude_tags=['"bili"'])
    text = render_l0_recent(got, chars=int(body.get("chars") or 400))
    return {"ok": True, "blocks": {"recent": text}, "text": text}


def recipe_batches(store, body: dict, embedder=None) -> dict:
    scope = str(body.get("scope") or "")
    got = batches(store, "L0", idle_seconds=float(body.get("idle_seconds") or 300),
                  want=int(body.get("batches") or 2), scope=scope,
                  limit=int(body.get("limit") or 300), exclude_tags=['"bili"'])
    text = render_batches(got, max_chars=int(body.get("max_chars") or 8000))
    return {"ok": True, "blocks": {"recent": text}, "text": text,
            "batches": len(got), "count": sum(len(b) for b in got)}


RECIPES = {
    "diary": recipe_diary,
    "review": recipe_review,
    "style": recipe_style,
    "profile": recipe_profile,
    "important": recipe_important,
    "evidence": recipe_evidence,
    "recall": recipe_recall,
    "recent": recipe_recent,
    "batches": recipe_batches,
}


def run(store, name: str, body: dict, embedder=None) -> dict:
    fn = RECIPES.get(str(name or "").strip().lower())
    if fn is None:
        return {"ok": False, "error": f"unknown recipe: {name}",
                "available": sorted(RECIPES)}
    return fn(store, body or {}, embedder)
