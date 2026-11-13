"""输入配方：所有「给模型看的素材」都在这里组装。

三层：

    原语   取行 / 检索 / 渲染（排版在 render.py）
    配方   每个用途声明一次要哪些块（本文件底部 RECIPES）
    入口   POST /input/<name>

消费方只调一次，不再自己拼 SQL、也不再调几个接口凑素材。
"""
from __future__ import annotations

import time

from render import (render_diary, render_diary_row, render_memory_line,
                    render_persona, strip_persona_links)


# ---------------------------------------------------------------------------
# 原语：取行
# ---------------------------------------------------------------------------

def _rows(store, sql: str, args: list) -> list:
    try:
        return list(store.conn.execute(sql, args).fetchall())
    except Exception:  # noqa: BLE001
        return []


def _text(row) -> str:
    try:
        return str(row["text"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def rows_l0(store, *, scope: str = "", session_id: str = "", since: float = 0.0,
            until: float | None = None, limit: int = 80,
            exclude_bili: bool = True) -> list:
    """原话。session_id 优先（只看当前会话），否则按 scope。"""
    sql = ["SELECT id,text,ts,tags,scope FROM memory WHERE tier='L0'"]
    args: list = []
    if session_id:
        sql.append("AND tags LIKE ?")
        args.append(f"%session:{session_id}%")
    elif scope:
        sql.append("AND (scope=? OR scope='global')")
        args.append(scope)
    if since:
        sql.append("AND ts>=?")
        args.append(float(since))
    if until:
        sql.append("AND ts<?")
        args.append(float(until))
    if exclude_bili:
        sql.append("AND tags NOT LIKE '%\"bili\"%'")
    sql.append("ORDER BY ts DESC LIMIT ?")
    args.append(max(1, int(limit)))
    return _rows(store, " ".join(sql), args)


def rows_tier(store, tier: str, *, scope: str = "", since: float = 0.0,
              until: float | None = None, limit: int = 40) -> list:
    sql = ["SELECT * FROM memory WHERE tier=?"]
    args: list = [tier]
    if scope:
        sql.append("AND (scope=? OR scope='global')")
        args.append(scope)
    if since:
        sql.append("AND ts>=?")
        args.append(float(since))
    if until:
        sql.append("AND ts<?")
        args.append(float(until))
    sql.append("ORDER BY ts DESC LIMIT ?")
    args.append(max(1, int(limit)))
    return _rows(store, " ".join(sql), args)


def batch_rows(rows: list, idle_seconds: float, want: int) -> list[list]:
    """把按时间倒序的行切成批次，取最近 want 批（返回旧的在前）。"""
    batches: list[list] = []
    cur: list = []
    prev_ts = None
    for row in rows:
        ts = float(row["ts"] or 0)
        if prev_ts is not None and prev_ts - ts > idle_seconds:
            if cur:
                batches.append(cur)
            cur = []
            if len(batches) >= want:
                break
        cur.append(row)
        prev_ts = ts
    if cur and len(batches) < want:
        batches.append(cur)
    return list(reversed(batches))


# ---------------------------------------------------------------------------
# 原语：渲染
# ---------------------------------------------------------------------------

def _cut_lines(lines: list[str], max_chars: int) -> str:
    """按整行累加，超了就不加 —— 不切在半句话上。"""
    out: list[str] = []
    total = 0
    for line in lines:
        if total + len(line) + 1 > max_chars:
            break
        out.append(line)
        total += len(line) + 1
    return "\n".join(out)


def render_evidence(items: list, l0_rows: list, *, l1_chars: int = 240,
                    l3_chars: int = 400, l0_chars: int = 400,
                    max_chars: int = 16000) -> str:
    """最近 L1/L3 一行一条，再附它们引用的原话。"""
    l1_lines: list[str] = []
    l3_lines: list[str] = []
    for item in items or []:
        line = str(item.get("line") or "").strip()
        if not line:
            line = render_memory_line(item, with_id=True, with_time=False)
        if not line:
            continue
        tier = str(item.get("tier") or "").upper()
        if tier == "L1":
            l1_lines.append(line[:l1_chars + 40])
        elif tier in ("L2", "L3", "L4"):
            l3_lines.append(line[:l3_chars + 40])

    l0_lines: list[str] = []
    seen: set[str] = set()
    for row in l0_rows or []:
        text = _text(row).replace("\n", " ")
        if not text:
            continue
        digest = text[:200]
        if digest in seen:
            continue
        seen.add(digest)
        l0_lines.append(text[:l0_chars])

    blocks: list[str] = []
    if l3_lines:
        blocks.append("【长期记忆】\n" + "\n".join(l3_lines))
    if l1_lines:
        blocks.append("【最近的便签】\n" + "\n".join(l1_lines))
    if l0_lines:
        blocks.append("【对应原话】\n" + "\n".join(f"- {x}" for x in l0_lines))
    return _cut_lines(blocks, max_chars)


def render_l0_recent(rows: list, *, chars: int = 400, max_chars: int = 16000) -> str:
    lines = []
    for row in rows or []:
        text = _text(row)
        if not text:
            continue
        lines.append(text[:chars])
    if not lines:
        return ""
    return "以下是最近的对话原话（按时间从早到晚）：\n" + _cut_lines(lines, max_chars)


def render_batches(batches: list[list], *, max_chars: int = 8000) -> str:
    blocks = []
    for batch in batches:
        lines = []
        for row in batch:
            text = _text(row)
            if not text:
                continue
            stamp = time.strftime("%m-%d %H:%M", time.localtime(float(row["ts"] or 0)))
            lines.append(f"[{stamp}] {text}")
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:max_chars]


def expand_persona_links(store, constitution: str) -> str:
    """把人格里的 【L3:123】 展开成「标题 · 状态 + 正文 + 当时的话」。

    复盘要判断一条还成不成立，得看见当时发生了什么；
    日常注入走 /persona 的 text，标记在那里已经抹掉了。
    """
    import re as _re

    text = str(constitution or "")
    ids = sorted({int(x) for x in _re.findall(r"【L3:(\d+)】", text)})
    if not ids:
        return text

    marks = ",".join("?" for _ in ids)
    rows = _rows(
        store,
        f"SELECT id,text,summary,thread_title,thread_status,source_ids "
        f"FROM memory WHERE tier IN ('L3','L4') AND id IN ({marks})",
        list(ids),
    )
    info = {int(r["id"]): r for r in rows}

    # 每条事件引用的原话
    quotes: dict[int, list[str]] = {}
    src_ids: set[int] = set()
    for r in rows:
        try:
            import json
            src_ids.update(int(x) for x in json.loads(r["source_ids"] or "[]"))
        except Exception:  # noqa: BLE001
            continue
    if src_ids:
        smarks = ",".join("?" for _ in src_ids)
        for r in _rows(store, f"SELECT id,text FROM memory WHERE tier='L0' AND id IN ({smarks})",
                       list(src_ids)):
            for mid, row in info.items():
                try:
                    import json
                    if int(r["id"]) in [int(x) for x in json.loads(row["source_ids"] or "[]")]:
                        quotes.setdefault(mid, []).append(_text(r)[:200])
                except Exception:  # noqa: BLE001
                    continue

    for mid in ids:
        row = info.get(mid)
        token = f"【L3:{mid}】"
        if row is None:
            text = text.replace(" " + token, "").replace(token, "")
            continue
        title = str(row["thread_title"] or "").strip() or "（无标题）"
        status = str(row["thread_status"] or "").strip() or "?"
        body = str(row["summary"] or row["text"] or "").strip().replace("\n", " ")[:200]
        lines = [f"〔{title} · {status}〕{body}"]
        got = quotes.get(mid) or []
        if got:
            lines.append("当时的话：" + " / ".join(got[:3]))
        text = text.replace(token, "\n    ".join(lines))
    return text


def persona_block(store, *, expand: bool = False) -> str:
    data = store.get_persona()
    constitution = str(data.get("constitution") or "")
    profile = str(data.get("user_profile") or "")
    if expand:
        constitution = expand_persona_links(store, constitution)
    return render_persona(constitution, profile)


# ---------------------------------------------------------------------------
# 配方
# ---------------------------------------------------------------------------

def _evidence_items(store, body: dict) -> dict:
    """L1/L3 行 + 它们引用的 L0（复用 hooks.evidence 的去重逻辑）。"""
    from api.routes.hooks import evidence as _evidence
    return _evidence(store, body)


def _refs(data: dict, limit: int = 8) -> list[str]:
    """这条输入引用了哪些条目，给「人格条目挂来源」用。"""
    out: list[str] = []
    for item in data.get("items") or []:
        tier = str(item.get("tier") or "")
        mid = item.get("id")
        if tier and mid is not None:
            out.append(f"{tier}:{mid}")
    for row in data.get("l0") or []:
        mid = row.get("id")
        if mid is not None:
            out.append(f"L0:{mid}")
    return out[:limit]


def _default_scope(store) -> str:
    return str((store.get_state() or {}).get("owner_scope") or "") or ""


def recipe_evidence(store, body: dict, embedder=None) -> dict:
    data = _evidence_items(store, body)
    text = render_evidence(data.get("items") or [], data.get("l0") or [])
    return {"ok": True, "blocks": {"evidence": text, "memories": text},
            "text": text, "refs": _refs(data)}


def _persona_and_evidence(store, body: dict, *, expand: bool, l1: int, l3: int,
                          l0: int, recent: int) -> dict:
    blocks: dict[str, str] = {}
    raw = store.get_persona()
    constitution = str(raw.get("constitution") or "")
    if expand:
        constitution = expand_persona_links(store, constitution)
    blocks["constitution"] = constitution
    blocks["profile"] = str(raw.get("user_profile") or "")
    blocks["persona"] = render_persona(
        constitution if expand else strip_persona_links(constitution),
        str(raw.get("user_profile") or ""),
    )
    data = _evidence_items(store, {
        "tiers": ["L1", "L3"],
        "limits": {"L1": l1, "L3": l3},
        "l0_limit": l0,
        "scope": body.get("scope") or "",
    })
    evidence_text = render_evidence(data.get("items") or [], data.get("l0") or [])
    blocks["evidence"] = evidence_text
    body["_refs"] = _refs(data)
    blocks["memories"] = evidence_text
    if recent:
        rows = rows_l0(store, scope=str(body.get("scope") or ""),
                       session_id=str(body.get("session_id") or ""), limit=recent)
        blocks["recent"] = render_l0_recent(rows)
    return blocks


def recipe_review(store, body: dict, embedder=None) -> dict:
    blocks = _persona_and_evidence(store, body, expand=True, l1=50, l3=30, l0=50, recent=30)
    rows = store.diary_list(int(body.get("diary_days") or 7))
    keep = [r for r in rows if str(r.get("date") or "")]
    blocks["diary"] = render_diary(list(reversed(keep)))
    return {"ok": True, "blocks": blocks, "refs": body.get("_refs") or [],
            "text": "\n\n".join(v for v in blocks.values() if v)}


def recipe_style(store, body: dict, embedder=None) -> dict:
    blocks = _persona_and_evidence(store, body, expand=False, l1=30, l3=20, l0=30, recent=60)
    blocks["material"] = blocks.get("evidence", "")

    return {"ok": True, "blocks": blocks, "refs": body.get("_refs") or [],
            "text": "\n\n".join(v for v in blocks.values() if v)}


def recipe_profile(store, body: dict, embedder=None) -> dict:
    blocks = _persona_and_evidence(store, body, expand=False, l1=50, l3=30, l0=50, recent=20)

    return {"ok": True, "blocks": blocks, "refs": body.get("_refs") or [],
            "text": "\n\n".join(v for v in blocks.values() if v)}


def recipe_important(store, body: dict, embedder=None) -> dict:
    blocks = _persona_and_evidence(store, body, expand=False, l1=15, l3=10, l0=50, recent=80)

    return {"ok": True, "blocks": blocks, "refs": body.get("_refs") or [],
            "text": "\n\n".join(v for v in blocks.values() if v)}


def recipe_diary(store, body: dict, embedder=None) -> dict:
    """昨天的日记素材：人格 + 昨天的便签 + 相关的旧事 + 前几天的日记。"""
    import datetime as _dt

    target = str(body.get("date") or "").strip()
    day = None
    if target:
        try:
            day = _dt.date.fromisoformat(target)
        except ValueError:
            day = None
    if day is None:
        day = _dt.date.today() - _dt.timedelta(days=1)
    start = _dt.datetime.combine(day, _dt.time.min).timestamp()
    end = start + 86400
    scope = str(body.get("scope") or "")

    blocks: dict[str, str] = {}
    blocks["persona"] = persona_block(store, expand=False)

    # 昨天的便签：全部，情绪只做附注
    l1_rows = rows_tier(store, "L1", scope=scope, since=start, until=end, limit=40)
    lines = []
    for row in reversed(l1_rows):
        text = _text(row)
        if not text:
            continue
        try:
            label = str(row["emotion_label"] or "").strip()
        except (KeyError, IndexError):
            label = ""
        lines.append(f"- （{label}）{text}" if label else f"- {text}")
    blocks["notes"] = "\n".join(lines)

    # 相关的旧事：拿昨天最近的几条便签去检索
    memory_lines: list[str] = []
    seen: set[str] = set()
    for row in l1_rows[:5]:
        query = _text(row)[:160]
        if not query:
            continue
        try:
            ctx = _context(store, {
                "query": query, "tiers": ["L3"], "limits": {"L3": 3},
                "top_k": 3, "scope": scope, "purpose": "diary",
                "max_chars": 800, "before_ts": start,
            }, embedder)
        except Exception:  # noqa: BLE001
            continue
        for line in str(ctx.get("text") or "").splitlines():
            line = line.strip()
            if not line.startswith("[记得的事"):
                continue
            key = line[:120]
            if key in seen:
                continue
            seen.add(key)
            memory_lines.append(line)
            if len(memory_lines) >= 5:
                break
        if len(memory_lines) >= 5:
            break
    blocks["memories"] = "\n".join(memory_lines)

    days = int(body.get("diary_days") or 7)
    rows = [r for r in store.diary_list(days + 2) if str(r.get("date") or "") < day.isoformat()]
    blocks["prev_diary"] = render_diary(rows[:days]) if rows else ""

    text = "\n\n".join(v for v in blocks.values() if v)
    return {"ok": True, "date": day.isoformat(), "blocks": blocks, "text": text}


def _context(store, body: dict, embedder=None) -> dict:
    from memory.context import build_context
    return build_context(store, body, embedder)


def recipe_recall(store, body: dict, embedder=None) -> dict:
    data = _context(store, {**body, "purpose": body.get("purpose") or "recall"}, embedder)
    return {"ok": True, "blocks": {"recall": str(data.get("text") or "")},
            "text": str(data.get("text") or ""), "count": data.get("count")}


def recipe_recent(store, body: dict, embedder=None) -> dict:
    session_id = str(body.get("session_id") or "")
    scope = str(body.get("scope") or "")
    if not session_id and not scope:
        return {"ok": True, "blocks": {"recent": ""}, "text": ""}
    rows = rows_l0(store, scope=scope, session_id=session_id,
                   since=float(body.get("since") or 0.0),
                   limit=int(body.get("limit") or 80))
    text = render_l0_recent(rows, chars=int(body.get("chars") or 400))
    return {"ok": True, "blocks": {"recent": text}, "text": text}


def recipe_batches(store, body: dict, embedder=None) -> dict:
    scope = str(body.get("scope") or "")
    idle = float(body.get("idle_seconds") or 300)
    want = max(1, min(6, int(body.get("batches") or 2)))
    rows = rows_l0(store, scope=scope, limit=int(body.get("limit") or 300))
    batches = batch_rows(rows, max(60.0, min(idle, 3600.0)), want)
    text = render_batches(batches, max_chars=int(body.get("max_chars") or 8000))
    return {"ok": True, "blocks": {"recent": text}, "text": text,
            "batches": len(batches), "count": sum(len(b) for b in batches)}


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
