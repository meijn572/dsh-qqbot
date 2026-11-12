"""本鱼的小面板：只读展示机器人状态、心情、记忆、表情包、日志。"""

import json
import os
import re
import socket
import urllib.request
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from settings import BOT_DIR as BOT, CMEM_BASE, DSH_HOME as HOME, HEALTH_FILE, PANEL_PORT, QR_FILE, STATE_FILE, WORKSPACE
from qqbot.domains.group.lexicon import (
    KINDS,
    STATUSES,
    delete_entry as delete_lexicon_entry,
    list_entries as list_lexicon_entries,
    upsert_entry as upsert_lexicon_entry,
)
from qqbot.domains.growth import proposals as growth_review
from qqbot.domains.media.library import clean_facets, clean_label
from qqbot.domains.media.meta import lookup_ref as resolve_sticker_ref

DB = HOME / "memory" / "memory.db"
PERSONA = HOME / "memory" / "persona-chat.md"
BILI = HOME / "bili-duty"
STICKERS = BOT / "stickers"
AUT_DIR = HOME / "bili-autonomy"
AUT_INTERESTS = AUT_DIR / "interests.json"
AUT_STATE = AUT_DIR / "state.json"
AUT_OUT = AUT_DIR / "out"
SLANG_DIR = HOME / "persona-roles" / "state"


def groupslang_payload() -> dict:
    groups: dict[str, list[dict]] = {}
    for entry in list_lexicon_entries(kind="slang"):
        scope = str(entry.get("scope") or "")
        if not scope.startswith("group:"):
            continue
        gid = scope.split(":", 1)[1]
        examples = entry.get("examples") or []
        groups.setdefault(gid, []).append({
            "term": entry.get("term") or "",
            "meaning": entry.get("meaning") or "",
            "example": examples[0] if examples else "",
            "aliases": entry.get("aliases") or [],
            "count": int(entry.get("count") or 0),
            "last_seen": int(entry.get("last_seen") or 0),
        })
    logs = {}
    log_dir = HOME / "group-log"
    if log_dir.is_dir():
        for path in log_dir.glob("*.jsonl"):
            try:
                logs[path.stem] = len(path.read_text(encoding="utf-8").splitlines())
            except Exception:  # noqa: BLE001
                logs[path.stem] = 0
    last = ""
    state_path = SLANG_DIR / "group-slang-state.json"
    if state_path.exists():
        try:
            last = str(json.loads(state_path.read_text(encoding="utf-8")).get("date") or "")
        except Exception:  # noqa: BLE001
            last = ""
    # 词库统一在 lexicon（slang 表已退役），这里读统一源
    learned = [x for x in list_lexicon_entries() if str(x.get("meaning") or "").strip()]
    return {"groups": groups, "logs": logs, "last_extract": last, "service_slang": learned}


def lexicon_payload() -> dict:
    entries = []
    for entry in list_lexicon_entries():
        scope = str(entry.get("scope") or "global")
        examples = entry.get("examples") or []
        category = "group" if scope.startswith("group:") else "network"
        entries.append({
            "id": entry.get("id") or "",
            "category": category,
            "kind": entry.get("kind") or "",
            "scope": scope.split(":", 1)[1] if category == "group" else "global",
            "status": entry.get("status") or "stable",
            "term": entry.get("term") or "",
            "aliases": entry.get("aliases") or [],
            "meaning": entry.get("meaning") or "",
            "example": examples[0] if examples else "",
            "count": int(entry.get("count") or 0),
            "last_seen": int(entry.get("last_seen") or 0),
        })
    entries.sort(key=lambda item: (item["kind"], item["category"], item["term"]))
    return {"entries": entries, "kinds": list(KINDS), "statuses": list(STATUSES)}


def lexicon_lookup_payload(query: str, scope: str = "", kind: str = "", status: str = "") -> dict:
    q = str(query or "").strip().lower()
    if not q:
        return {"query": "", "terms": []}
    wanted_scope = str(scope or "").strip()
    if wanted_scope.startswith("group:"):
        wanted_scope = wanted_scope.split(":", 1)[1]
    out = []
    for item in lexicon_payload().get("entries") or []:
        if scope and str(item.get("scope") or "") != wanted_scope:
            continue
        if kind and str(item.get("kind") or "") != kind:
            continue
        if status and str(item.get("status") or "") != status:
            continue
        fields = [str(item.get("term") or ""), " ".join(item.get("aliases") or []), str(item.get("meaning") or "")]
        hay = " ".join(fields).lower()
        if q not in hay:
            continue
        score = 0
        if q == str(item.get("term") or "").lower() or q in [str(a).lower() for a in (item.get("aliases") or [])]:
            score += 100
        elif q in str(item.get("term") or "").lower():
            score += 50
        if q in str(item.get("meaning") or "").lower():
            score += 20
        out.append((score, item))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return {"query": q, "terms": [item for _, item in out[:20]]}


def lexicon_search_payload(query: str) -> dict:
    q = str(query or "").strip().lower()
    if not q:
        return {"query": "", "terms": [], "stickers": []}
    terms = lexicon_lookup_payload(q).get("terms") or []
    stickers = []
    for item in sticker_payload().get("items") or []:
        facet_hay = " ".join([
            " ".join(str(t) for t in (item.get("identity") or [])),
            " ".join(str(t) for t in (item.get("action") or [])),
            " ".join(str(t) for t in (item.get("expression") or [])),
            " ".join(str(t) for t in (item.get("generic") or [])),
        ]).lower()
        caption = str(item.get("caption") or "").lower()
        if q in facet_hay or (q not in facet_hay and q in caption):
            stickers.append(item)
    return {
        "query": q,
        "terms": terms[:8],
        "stickers": stickers[:8],
    }


def lexicon_add(kind: str, term: str, meaning: str, example: str = "", aliases: str | list = "",
                status: str = "stable", scope: str = "") -> dict:
    term = str(term or "").strip()[:40]
    meaning = str(meaning or "").strip()[:300]
    example = str(example or "").strip()[:300]
    kind = str(kind or "meme").strip()
    status = str(status or "stable").strip()
    if kind not in KINDS:
        kind = "meme"
    if status not in STATUSES:
        status = "stable"
    if isinstance(aliases, str):
        aliases = [x.strip() for x in re.split(r"[,，、\s]+", aliases) if x.strip()]
    aliases = [str(x).strip()[:40] for x in (aliases or []) if str(x).strip()][:12]
    if not term:
        return {"ok": False, "error": "term required"}
    if not scope:
        if kind == "slang":
            config = read_json(BOT / "config.json") or {}
            groups = config.get("allowed_groups") or []
            if not groups:
                return {"ok": False, "error": "没有配置群号"}
            scope = f"group:{groups[0]}"
        else:
            scope = "global"
    entry = upsert_lexicon_entry(
        term,
        kind=kind,
        scope=scope,
        status=status,
        meaning=meaning,
        aliases=aliases,
        examples=[example] if example else [],
        source="panel",
    )
    if not entry:
        return {"ok": False, "error": "写入失败"}
    return {"ok": True, "id": entry.get("id"), "entry": entry}


def lexicon_delete(entry_id: str = "", category: str = "", term: str = "") -> dict:
    entry_id = str(entry_id or "").strip()
    if entry_id:
        return {"ok": delete_lexicon_entry(entry_id)}
    term = str(term or "").strip()
    if not term:
        return {"ok": False, "error": "id required"}
    targets = list_lexicon_entries()
    if category == "group":
        config = read_json(BOT / "config.json") or {}
        groups = config.get("allowed_groups") or []
        scope = f"group:{groups[0]}" if groups else ""
        targets = [e for e in targets if e.get("scope") == scope]
    elif category == "network":
        targets = [e for e in targets if e.get("scope") == "global"]
    target = next((e for e in targets if e.get("term") == term), None)
    if not target:
        return {"ok": False, "error": "没找到词条"}
    return {"ok": delete_lexicon_entry(str(target.get("id") or ""))}


PORTS = {
    "DSH 实例": 60773,
    "记忆服务": 8081,
    "OneBot WS": 3001,
    "OneBot HTTP": 3000,
    "AstrBot 面板": 6185,
    "AstrBot WS": 6199,
}


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.15)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def tail(path: Path, n: int = 120) -> str:
    if not path.exists():
        return "(文件不存在)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError as exc:
        return f"(读取失败: {exc})"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def cmem_get(path: str) -> dict:
    try:
        with urllib.request.urlopen(CMEM_BASE + path, timeout=4) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def health() -> dict:
    data = read_json(HEALTH_FILE)
    if not data:
        return {"alive": False, "age": None}
    age = time.time() - int(data.get("ts", 0)) / 1000
    return {"alive": age < 120, "age": round(age, 1), "pid": data.get("pid")}


def mood_payload() -> dict:
    state = cmem_get("/state")
    rel = state.get("relationship") or {}
    if not isinstance(rel, dict):
        rel = {}
    emotion = state.get("emotion") or {}
    dims = {}
    if isinstance(emotion, dict):
        for key, value in list(emotion.items())[:7]:
            if str(key) in ("valence", "arousal"):
                continue
            try:
                dims[str(key)] = round(float(value) * 100)
            except (TypeError, ValueError):
                continue
    timeline = []
    for item in (state.get("emotion_recent") or [])[-12:]:
        if isinstance(item, dict):
            timeline.append({
                "at": item.get("at") or item.get("ts"),
                "mood": item.get("label") or item.get("mood") or "",
                "reason": item.get("trigger") or item.get("reason") or "",
                "source": item.get("source") or "",
            })
    # 服务返回的 emotion_recent 是最新在前；最近一次应取第一条
    last_emotion = timeline[0] if timeline else {}
    # 情绪只来自 L1：取最近一条的 valence 当心情条位置，没有就中性
    last_v = float((state.get("emotion_recent") or [{}])[0].get("valence") or 0)
    return {
        "configured": bool(state),
        "owner": "九歌",
        "self": "大肥鱼",
        "inject_mode": "dsh-remembers",
        "auto_judge": True,
        "per_day": 0,
        "mood": round((last_v + 1) * 50),
        "dims": dims,
        "reason": str(last_emotion.get("reason") or state.get("activity") or ""),
        "emotion_label": str(last_emotion.get("mood") or ""),
        "confidence": 50,
        "updated_at": state.get("last_interaction") or 0,
        "timeline": timeline,
        "active": state.get("mood") or "",
        "relationship": rel,
        "activity": state.get("activity", ""),
        "valence": last_v,
    }


STYLE_PROPOSAL = HOME / "persona-roles" / "state" / "style-proposal.json"
STYLE_BEGIN = "<!-- style:begin -->"
STYLE_END = "<!-- style:end -->"
STYLE_HEADING = "## 表现"


def _style_block(constitution: str) -> str:
    text = str(constitution or "")
    match = re.search(re.escape(STYLE_BEGIN) + r"(.*?)" + re.escape(STYLE_END), text, re.S)
    if match:
        return match.group(1).strip()
    match = re.search(r"## 表现\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    return match.group(1).strip() if match else ""


def cmem_post(path: str, body: dict) -> dict:
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(CMEM_BASE + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def review_payload() -> dict:
    items = []
    for item in growth_review.pending():
        op = (item.get("ops") or [{}])[0]
        items.append({
            "id": item.get("id"),
            "target": item.get("target"),
            "op": op.get("op") or "add",
            "text": op.get("text") or "",
            "from": op.get("from") or "",
            "reason": item.get("reason") or "",
            "evidence": item.get("evidence") or [],
            "created_at": item.get("created_at") or 0,
        })
    return {"items": items, "count": len(items)}


def review_commitment(item: str, reason: str = "") -> dict:
    proposal = growth_review.add_commitment(item, reason=reason)
    return {"ok": proposal is not None, "proposal": proposal}


def review_reject(proposal_id: str) -> dict:
    return {"ok": growth_review.set_status(str(proposal_id or ""), "rejected")}


def _apply_section_ops(constitution: str, heading: str, ops: list[dict]) -> str:
    match = re.search(r"(" + re.escape(heading) + r"\s*\n)(.*?)(?=\n## |\Z)", constitution, re.S)
    if not match:
        raise ValueError(f"核心设定里没有 {heading}")
    bullets = [line for line in match.group(2).splitlines() if line.strip().startswith("- ")]
    for op in ops:
        kind = str(op.get("op") or "add")
        text = str(op.get("text") or "").strip()
        old = str(op.get("from") or "").strip()
        if not text:
            continue
        # 关联事件：写成 【L3:123】，日常渲染时抹掉，面板/复盘才用
        src = str(op.get("source") or "").strip()
        suffix = f" 【L3:{src}】" if src.isdigit() else ""
        if kind == "add":
            bullets.append("- " + text + suffix)
        elif kind == "modify":
            target = "- " + old if old else ""
            hit = next((i for i, line in enumerate(bullets) if line.strip() == target), None)
            if hit is None:
                raise ValueError(f"找不到要修改的旧句：{old}")
            bullets[hit] = "- " + text + suffix
        elif kind == "remove":
            target = "- " + (old or text)
            bullets = [line for line in bullets if line.strip() != target]
    body = "\n".join(bullets)
    return constitution[:match.start(2)] + body + constitution[match.end(2):]


def review_apply(proposal_id: str) -> dict:
    target_item = next((x for x in growth_review.load_proposals() if x.get("id") == proposal_id), None)
    if not target_item or target_item.get("status") != "pending":
        return {"ok": False, "error": "候选不存在或已处理"}
    target = str(target_item.get("target") or "")
    ops = target_item.get("ops") or []
    if target == "commitment":
        text = str((ops[0] if ops else {}).get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "约定为空"}
        result = cmem_post("/persona/important", {"action": "add", "item": text})
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "写入失败"}
        growth_review.set_status(proposal_id, "applied")
        return {"ok": True, "target": target}
    if target not in ("preference", "judgment", "relationship", "weakness"):
        return {"ok": False, "error": "未知目标"}
    persona = cmem_get("/persona")
    constitution = str(persona.get("constitution") or "")
    heading = {
        "preference": "## 偏好",
        "judgment": "## 价值取向",
        "relationship": "## 我们怎么对彼此",
        "weakness": "## 弱点",
    }[target]
    try:
        new_constitution = _apply_section_ops(constitution, heading, ops)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    backup = HOME / "persona-roles" / "state" / f"constitution-before-review-{time.strftime('%Y%m%d-%H%M%S')}.md"
    backup.write_text(constitution, encoding="utf-8")
    result = cmem_post("/persona", {"constitution": new_constitution})
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "写入失败"}
    growth_review.set_status(proposal_id, "applied")
    return {"ok": True, "target": target, "backup": backup.name}


def style_payload() -> dict:
    proposal = {}
    if STYLE_PROPOSAL.exists():
        proposal = read_json(STYLE_PROPOSAL)
    persona = cmem_get("/persona")
    constitution = str(persona.get("constitution") or "")
    current = _style_block(constitution)
    return {"proposal": proposal, "current": current}


def apply_style() -> dict:
    if not STYLE_PROPOSAL.exists():
        return {"ok": False, "error": "没有待处理的风格提议"}
    proposal = read_json(STYLE_PROPOSAL)
    style = str(proposal.get("style") or "").strip()
    if not style:
        return {"ok": False, "error": "提议为空"}
    persona = cmem_get("/persona")
    constitution = str(persona.get("constitution") or "")
    if STYLE_BEGIN in constitution and STYLE_END in constitution:
        new_constitution = re.sub(
            re.escape(STYLE_BEGIN) + r".*?" + re.escape(STYLE_END),
            lambda _: STYLE_BEGIN + "\n" + style + "\n" + STYLE_END,
            constitution, count=1, flags=re.S)
    else:
        match = re.search(r"(## 表现\s*\n)(.*?)(?=\n## |\Z)", constitution, re.S)
        if not match:
            return {"ok": False, "error": "核心设定里没有「## 表现」段"}
        new_constitution = constitution[:match.start(2)] + STYLE_BEGIN + "\n" + style + "\n" + STYLE_END + constitution[match.end(2):]
    backup = HOME / "persona-roles" / "state" / f"constitution-before-style-{time.strftime('%Y%m%d-%H%M%S')}.md"
    backup.write_text(constitution, encoding="utf-8")
    result = cmem_post("/persona", {"constitution": new_constitution})
    if result.get("ok"):
        STYLE_PROPOSAL.unlink(missing_ok=True)
        return {"ok": True, "message": "已应用新风格", "backup": backup.name}
    return {"ok": False, "error": result.get("error") or "写入失败"}


def dismiss_style() -> dict:
    STYLE_PROPOSAL.unlink(missing_ok=True)
    return {"ok": True, "message": "已忽略风格提议"}


def proactive_payload() -> dict:
    return cmem_get("/proactive") or {"enabled": False, "error": "记忆服务未连接"}


def set_proactive(body: dict) -> dict:
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(CMEM_BASE + "/proactive", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def memory_payload() -> dict:
    out = {"count": 0, "items": [], "persona_chars": 0,
           "stats": {"tiers": {}, "l3_status": {}}}
    data = cmem_get("/memories?limit=100")
    if data:
        out["count"] = int(data.get("total") or 0)
        seen = set()

        def add(item):
            tier = str(item.get("tier") or "")
            key = (tier, item.get("id")) if item.get("id") else (
                tier, str(item.get("text") or ""), item.get("ts"))
            if key in seen:
                return
            seen.add(key)
            out["items"].append({
                "id": item.get("id"),
                "type": tier,
                "content": str(item.get("summary") or item.get("text") or ""),
                "title": str(item.get("thread_title") or ""),
                "status": str(item.get("l2_status") or item.get("thread_status") or ""),
                "l2_status": str(item.get("l2_status") or ""),
                "confidence": item.get("confidence"),
                "expires_at": item.get("expires_at"),
                "time": item.get("ts") or "",
                "last_seen": item.get("thread_last_seen_at") or "",
                "stale": bool(item.get("stale_at")),
                "source_count": len(item.get("source_ids") or []),
                "insight_target": str(item.get("insight_target") or ""),
                # L1 的新字段：情绪、留下没说完的两样
                "emotion_label": str(item.get("emotion_label") or ""),
                "emotion_valence": item.get("emotion_valence"),
                "emotion_arousal": item.get("emotion_arousal"),
                "want_more": str(item.get("want_more") or ""),
                "ask_him": str(item.get("ask_him") or ""),
                "want_used": bool(item.get("want_used")),
                "memorability": item.get("memorability"),
                "dominant": str(item.get("dominant") or ""),
                "last_recalled_at": item.get("last_recalled_at") or "",
                "active_until": item.get("active_until") or "",
                "recall_count": int(item.get("recall_count") or 0),
                "stability_days": item.get("stability_days"),
            })
            out["stats"]["tiers"][tier] = out["stats"]["tiers"].get(tier, 0) + 1
            if tier == "L3":
                st = str(item.get("thread_status") or "legacy")
                out["stats"]["l3_status"][st] = out["stats"]["l3_status"].get(st, 0) + 1

        for item in data.get("items") or []:
            add(item)
        # L3 跨天、时间老，可能不在最近 100 条里；单独取全量
        l3 = cmem_get("/memories?tier=L3&limit=200")
        for item in (l3 or {}).get("items") or []:
            add(item)
        # 核心记忆时间很老，可能不在最近 100 条里
        core = cmem_get("/memories?tier=L4&limit=100")
        for item in (core or {}).get("items") or []:
            add(item)
        persona = cmem_get("/persona")
        chars = persona.get("chars") or {}
        out["persona_chars"] = int(chars.get("constitution") or 0)
        # 层级总数用服务端 counts，不用“已加载条数”
        counts = data.get("counts") or {}
        if counts:
            out["stats"]["tiers"] = {str(k): int(v) for k, v in counts.items()}
        return out
    return out


def guests_payload() -> dict:
    data = cmem_get("/profiles") or {}
    profiles = data.get("profiles") or []
    config = read_json(BOT / "config.json") or {}
    owners = {str(uid) for uid in (config.get("allowed_users") or [])}
    out = []
    for profile in profiles[:80]:
        uid = str(profile.get("user_id") or "")
        if uid in owners:
            continue
        score = 0
        if uid:
            aff = cmem_get("/affinity?user=" + uid)
            score = aff.get("score") or 0
        out.append({
            "user_id": uid,
            "name": str(profile.get("name") or ""),
            "msg_count": int(profile.get("msg_count") or 0),
            "profile": str(profile.get("profile") or ""),
            "manual_profile": str(profile.get("manual_profile") or ""),
            "affinity": float(score or 0),
            "updated": profile.get("updated_at") or 0,
        })
    out.sort(key=lambda item: (item["affinity"], item["msg_count"]), reverse=True)
    return {"profiles": out, "admins": data.get("admins") or []}


def notebook_payload() -> dict:
    # 小本子需要 id 才能点“结束”，不带 id 的 /threads/open 留给模型工具
    data = cmem_get("/memories?tier=L3&limit=200") or {}
    open_threads = []
    for item in data.get("items") or []:
        if str(item.get("thread_status") or "") != "open":
            continue
        open_threads.append({
            "id": item.get("id"),
            "title": str(item.get("thread_title") or ""),
            "status": "open",
            "last_seen_at": item.get("thread_last_seen_at") or item.get("ts") or 0,
        })
    open_threads.sort(key=lambda x: float(x.get("last_seen_at") or 0), reverse=True)
    return {
        "notes": cmem_get("/notes") or [],
        "tasks": cmem_get("/tasks") or [],
        "diary": cmem_get("/diary") or [],
        "open_threads": open_threads[:8],
    }


def close_thread(thread_id) -> dict:
    try:
        mid = int(thread_id)
    except Exception:
        return {"ok": False, "error": "invalid id"}
    if mid <= 0:
        return {"ok": False, "error": "invalid id"}
    return cmem_post("/threads/close", {"id": mid})


def update_memory_text(mem_id, text) -> dict:
    try:
        mid = int(mem_id)
    except Exception:
        return {"ok": False, "error": "invalid id"}
    body = str(text or "").strip()
    if mid <= 0 or not body:
        return {"ok": False, "error": "id and text required"}
    return cmem_post("/memories/update_text", {"id": mid, "text": body})


def _render_links(constitution: str) -> str:
    """把 【L3:123】 换成「标题」，面板点得开。

    查不到的就抹掉，不留一串数字在界面上。
    """
    text = str(constitution or "")
    ids = sorted({int(x) for x in re.findall(r"【L3:(\d+)】", text)})
    if not ids:
        return text
    titles: dict[int, str] = {}
    # 关联既能指 L3（事件）也能指 L4（核心事件）
    for tier in ("L3", "L4"):
        try:
            data = cmem_get(f"/memories?tier={tier}&limit=200")
            for item in (data.get("items") or []):
                try:
                    mid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                if mid in ids:
                    titles[mid] = str(item.get("thread_title") or "").strip()
        except Exception:  # noqa: BLE001
            continue
    for mid in ids:
        title = titles.get(mid) or ""
        if not title:
            # 查不到标题（迁移过的旧记录）就抹掉，不留「旧事件」这种噪音
            text = text.replace(" 【L3:%d】" % mid, "").replace("【L3:%d】" % mid, "")
        else:
            text = text.replace("【L3:%d】" % mid, f"〔{title}〕")
    return text


SELF_SECTIONS = ("我是谁", "表现", "偏好", "价值取向", "弱点")
OTHER_SECTIONS = ("我们怎么过", "我们怎么对彼此", "我们之间有什么")


def _split_constitution(text: str) -> dict[str, str]:
    """把核心设定按 ## 切成 {标题: 正文}。"""
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in str(text or "").splitlines():
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur = line[3:].strip()
            buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def persona_payload() -> dict:
    persona = cmem_get("/persona")
    if not persona:
        return {"text": "(记忆服务未连接)", "sections": {}, "growth": "", "growth_chars": 0,
                "important": [], "proposals": {}, "history": [], "role": "大肥鱼"}
    constitution = str(persona.get("constitution") or "")
    # 面板里把 【L3:123】 换成能点开的标题
    display = _render_links(constitution)
    text = display
    # 面板按「我自己 / 我和他」两大块展示，每块里再分小节
    parts = _split_constitution(display)
    blocks = {
        "self": [{"title": k, "body": parts.get(k, "")}
                 for k in SELF_SECTIONS if parts.get(k)],
        "other": ([{"title": "我眼中的他", "body": str(persona.get("user_profile") or "")}]
                  + [{"title": k, "body": parts.get(k, "")}
                     for k in OTHER_SECTIONS if parts.get(k)]),
    }
    try:
        rel = cmem_get("/state") or {}
        rel = (rel.get("relationship") or {}) if isinstance(rel, dict) else {}
    except Exception:  # noqa: BLE001
        rel = {}
    recent_relationship = {
        "summary": str(rel.get("summary") or ""),
        "date": str(rel.get("date") or ""),
        "updated_at": float(rel.get("updated_at") or 0),
    }
    return {
        "text": text,
        "blocks": blocks,
        "recent_relationship": recent_relationship,
        "role": "大肥鱼",
        "sections": {"identity": display, "style": "", "relationship": ""},
        "important": [],
        "proposals": {},
        "history": [],
        "constitution": constitution,
        "constitution_display": display,
        "user_profile": str(persona.get("user_profile") or ""),
        "identity": str(persona.get("identity") or "大肥鱼"),
        "self_image": str(persona.get("self_image") or ""),
        "chars": persona.get("chars") or {},
    }


def save_core_setting(text: str) -> dict:
    text = str(text or "")
    if len(text) > 15000:
        return {"ok": False, "error": "核心设定最多 15000 字"}
    try:
        data = cmem_post("/persona", {"constitution": text})
        return {"ok": True, "chars": len(text), "constitution": data.get("constitution", text)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def save_persona_field(field: str, text: str) -> dict:
    """手工编辑自我认知 / 用户画像。"""
    field = str(field or "")
    text = str(text or "").strip()
    if field == "self_model":
        return {"ok": False, "error": "自我认知已退场，改用日记"}
    if field == "user_profile":
        if len(text) > 8000:
            return {"ok": False, "error": "用户画像最多 8000 字"}
        try:
            data = cmem_post("/persona/user", {"user_profile": text})
            if data.get("ok") is False:
                return {"ok": False, "error": data.get("error") or "保存失败"}
            return {"ok": True, "field": field, "chars": len(text),
                    "user_profile": text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "未知字段"}


def sticker_payload() -> dict:
    categories = {}
    user_items = []
    items = []
    meta = read_json(STICKERS / "meta.json") or {}
    meta = {str(k).replace("\\", "/"): v for k, v in meta.items() if isinstance(v, dict)}
    hidden = 0
    if STICKERS.is_dir():
        for folder in sorted(STICKERS.iterdir()):
            if not folder.is_dir():
                continue
            files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in {".gif", ".png", ".jpg", ".jpeg", ".webp"}]
            stickers = []
            for f in files:
                rel = str(f.relative_to(STICKERS)).replace("\\", "/")
                if (meta.get(rel) or {}).get("sticker"):
                    stickers.append(f)
                elif f.name.startswith("u_"):
                    hidden += 1
            user = [f for f in stickers if f.name.startswith("u_")]
            if stickers:
                categories[folder.name] = {"total": len(stickers), "user": len(user)}
            for f in stickers:
                rel = str(f.relative_to(STICKERS)).replace("\\", "/")
                if f in user:
                    user_items.append({"file": rel, "category": folder.name, "size": f.stat().st_size})
                items.append({"file": rel, "category": folder.name, "size": f.stat().st_size})
    index = read_json(STICKERS / "index.json") or []
    index_map = {
        str(e.get("file") or "").replace("\\", "/"): e
        for e in index if isinstance(e, dict)
    }
    for item in items:
        entry = index_map.get(item["file"], {})
        item["caption"] = entry.get("caption", "")
        item["label"] = entry.get("label") or ""
        item["identity"] = entry.get("identity") if isinstance(entry.get("identity"), list) else []
        item["action"] = entry.get("action") if isinstance(entry.get("action"), list) else []
        item["expression"] = entry.get("expression") if isinstance(entry.get("expression"), list) else []
        item["generic"] = entry.get("generic") if isinstance(entry.get("generic"), list) else []
        item["meta_status"] = str(entry.get("meta_status") or "pending_review")
        item["meta_source"] = str(entry.get("meta_source") or "")
        item["reviewed_at"] = int(entry.get("reviewed_at") or 0)
        item["usage_count"] = int(entry.get("usage_count") or 0)
    item_map = {item["file"]: item for item in items}
    user_items = [item_map[x["file"]] for x in user_items if x["file"] in item_map]
    items.sort(key=lambda x: (x["category"], str(x.get("label") or x["file"])))
    user_items.sort(key=lambda x: x["file"], reverse=True)
    return {"categories": categories, "items": items[:200], "user_items": user_items[:60], "hidden_images": hidden}


def _sticker_file(rel: str) -> tuple[Path | None, str]:
    raw = str(rel or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or ".." in raw.split("/"):
        return None, ""
    candidate = (STICKERS / raw).resolve()
    if STICKERS.resolve() not in candidate.parents or not candidate.is_file():
        return None, ""
    return candidate, raw


def sticker_delete(rel: str) -> dict:
    path, key = _sticker_file(rel)
    if path is None:
        return {"ok": False, "error": "文件不存在或路径不合法"}
    try:
        path.unlink()
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    index = read_json(STICKERS / "index.json") or []
    if isinstance(index, list):
        index = [e for e in index if not (isinstance(e, dict) and str(e.get("file") or "").replace("\\", "/") == key)]
        (STICKERS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = read_json(STICKERS / "meta.json") or {}
    if isinstance(meta, dict):
        for old in (key, key.replace("/", "\\")):
            meta.pop(old, None)
        (STICKERS / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "file": key}


def sticker_lookup_payload(ref: str) -> dict:
    try:
        return resolve_sticker_ref(str(ref or ""))
    except Exception as exc:  # noqa: BLE001
        return {"found": False, "error": str(exc)}


def sticker_update_semantics(rel: str, label: str = "", identity: list | None = None,
                             action: list | None = None, expression: list | None = None,
                             generic: list | None = None) -> dict:
    path, key = _sticker_file(rel)
    if path is None:
        return {"ok": False, "error": "文件不存在或路径不合法"}
    index = read_json(STICKERS / "index.json") or []
    if not isinstance(index, list):
        index = []
    entry = next((e for e in index if isinstance(e, dict) and str(e.get("file") or "").replace("\\", "/") == key), None)
    if entry is None:
        entry = {"file": key, "category": path.parent.name, "caption": ""}
        index.append(entry)
    entry["label"] = clean_label(label)
    for field, values in (("identity", identity), ("action", action), ("expression", expression), ("generic", generic)):
        entry[field] = clean_facets(values)
    entry["meta_status"] = "reviewed"
    entry["meta_source"] = "panel"
    entry["reviewed_at"] = int(time.time())
    (STICKERS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "file": key, "label": entry["label"], **{k: entry[k] for k in ("identity", "action", "expression", "generic")}}


def interests_payload() -> dict:
    interests = []
    if AUT_INTERESTS.exists():
        try:
            interests = json.loads(AUT_INTERESTS.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001
            interests = []
    state = {}
    if AUT_STATE.exists():
        try:
            state = json.loads(AUT_STATE.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            state = {}
    reports = []
    if AUT_OUT.is_dir():
        for item in sorted(AUT_OUT.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            reports.append({"name": item.name, "size": item.stat().st_size, "time": int(item.stat().st_mtime)})
    latest = ""
    if reports:
        latest = tail(AUT_OUT / reports[0]["name"], 80)
    return {"interests": interests, "state": state, "reports": reports, "latest": latest}


def bili_feed_payload() -> dict:
    import re

    seen: list[dict] = []
    seen_file = BILI / "seen.md"
    if seen_file.exists():
        for line in seen_file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(BV\w+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*(挑了|跳过)\s*\|", line)
            if match:
                seen.append(
                    {
                        "date": match.group(1),
                        "bvid": match.group(2),
                        "title": match.group(3).strip(),
                        "up": match.group(4).strip(),
                        "status": match.group(5),
                        "url": f"https://www.bilibili.com/video/{match.group(2)}",
                    }
                )
    notes: list[dict] = []
    if AUT_OUT.is_dir():
        for report in sorted(AUT_OUT.glob("*.md"), reverse=True):
            text = report.read_text(encoding="utf-8", errors="replace")
            for section in re.split(r"(?m)^## ", text):
                section = section.strip()
                if not section:
                    continue
                head, _, body = section.partition("\n")
                videos = []
                for line in body.splitlines():
                    vm = re.match(r"-\s*(.+?)\s+(https?://\S+|`?BV[0-9A-Za-z]+`?)\s*(?:—\s*(.*))?$", line.strip())
                    if not vm:
                        continue
                    raw_link = vm.group(2).strip("`")
                    url = raw_link if raw_link.startswith("http") else f"https://www.bilibili.com/video/{raw_link}"
                    videos.append({"title": vm.group(1).strip(), "url": url, "why": (vm.group(3) or "").strip()})
                thought = " ".join(line.lstrip("> ").strip() for line in body.splitlines() if line.strip().startswith(">"))
                if videos:
                    notes.append({"head": head.strip(), "videos": videos, "thought": thought})
    interests = []
    if AUT_INTERESTS.exists():
        try:
            interests = json.loads(AUT_INTERESTS.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001
            interests = []
    activities = []
    data = cmem_get("/activity?kind=bili&limit=50")
    if isinstance(data, list):
        for item in data:
            activities.append({
                "id": item.get("id"),
                "time": item.get("ts") or "",
                "detail": str(item.get("detail") or ""),
                "summary": str(item.get("summary") or ""),
                "thought": str(item.get("thought") or ""),
                "insight": str(item.get("insight") or ""),
                "l3_id": item.get("l3_id"),
                "shared": bool(item.get("shared")),
            })
    return {"seen": seen[:40], "notes": notes[:20], "interests": interests[:10],
            "activities": activities, "login": bili_payload()}


def bili_payload() -> dict:
    cred = BILI / "bili_credential.json"
    logged_in = False
    uid = ""
    if cred.exists():
        try:
            data = json.loads(cred.read_text(encoding="utf-8"))
            logged_in = bool(data.get("sessdata"))
            uid = str(data.get("dedeuserid") or "")
        except Exception:  # noqa: BLE001
            pass
    return {"logged_in": logged_in, "uid": uid, "duty_tail": tail(BILI / "duty.log", 40)}


def qr_status() -> dict:
    out_file = BOT / "bili_login.out"
    state = ""
    if out_file.exists():
        text = out_file.read_text(encoding="utf-8", errors="replace")
        if "LOGIN_DONE" in text:
            state = "登录成功"
        elif "TIMEOUT" in text:
            state = "二维码已过期"
        elif "STATE_SCANNED" in text:
            state = "已扫码，等确认"
        elif "QR_SAVED" in text:
            state = "等待扫码"
    valid = False
    cred = BILI / "bili_credential.json"
    if cred.exists():
        try:
            valid = bool(json.loads(cred.read_text(encoding="utf-8")).get("sessdata"))
        except Exception:  # noqa: BLE001
            valid = False
    qr = QR_FILE
    return {
        "state": state or "未生成",
        "credential": valid,
        "qr_ready": qr.exists(),
        "mtime": int(qr.stat().st_mtime) if qr.exists() else 0,
    }


def status_payload() -> dict:
    st = read_json(STATE_FILE)
    bindings = {}
    for key, value in st.items():
        if isinstance(value, dict):
            bindings[key] = {"session": value.get("sid", ""), "seq": value.get("seq", 0)}
        else:
            bindings[key] = {"session": value, "seq": 0}
    mood = mood_payload()
    with ThreadPoolExecutor(max_workers=len(PORTS)) as pool:
        port_status = dict(zip(PORTS, pool.map(port_open, PORTS.values())))
    return {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ports": port_status,
        "bridge": health(),
        "bindings": bindings,
        "mood": mood.get("mood"),
        "mood_reason": mood.get("reason", ""),
        "relationship": (mood.get("relationship") or {}).get("summary", ""),
        "activity": mood.get("activity", ""),
        "proactive": (proactive_payload() or {}).get("enabled", False),
        "stickers_user": sum(1 for _ in STICKERS.rglob("u_*")) if STICKERS.is_dir() else 0,
        "bili_logged_in": bili_payload()["logged_in"],
        "memory_count": memory_payload()["count"],
    }
