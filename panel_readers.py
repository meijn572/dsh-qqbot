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

from settings import AGENTS, BOT_DIR as BOT, CMEM_BASE, DSH_HOME as HOME, HEALTH_FILE, PANEL_PORT, QR_FILE, SCRIPTS_DIR, STATE_FILE, WORKSPACE
from qqbot.domains.concepts import concept_id, ensure_concept
from qqbot.domains.group.lexicon import (
    KINDS,
    STATUSES,
    delete_entry as delete_lexicon_entry,
    list_entries as list_lexicon_entries,
    upsert_entry as upsert_lexicon_entry,
)
from qqbot.domains.media.meta import lookup_ref as resolve_sticker_ref

DB = HOME / "memory" / "memory.db"
PERSONA = HOME / "memory" / "persona-chat.md"
BILI = HOME / "bili-duty"
STICKERS = BOT / "stickers"
ROLE_DIR = HOME / "persona-roles"
ROLE_CARD = ROLE_DIR / "roles" / "小肥鱼.md"
ROLE_HISTORY = ROLE_DIR / "roles" / ".history"
AUT_DIR = HOME / "bili-autonomy"
AUT_INTERESTS = AUT_DIR / "interests.json"
AUT_STATE = AUT_DIR / "state.json"
AUT_OUT = AUT_DIR / "out"
SLANG_DIR = HOME / "group-slang"


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
    state_path = SLANG_DIR / "state.json"
    if state_path.exists():
        try:
            last = str(json.loads(state_path.read_text(encoding="utf-8")).get("date") or "")
        except Exception:  # noqa: BLE001
            last = ""
    learned = cmem_get("/slang") or []
    learned = [
        item for item in learned
        if str(item.get("meaning") or "").strip() or int(item.get("count") or 0) >= 2
    ]
    return {"groups": groups, "logs": logs, "last_extract": last, "service_slang": learned}


def lexicon_payload() -> dict:
    entries = []
    for entry in list_lexicon_entries():
        scope = str(entry.get("scope") or "global")
        examples = entry.get("examples") or []
        category = "group" if scope.startswith("group:") else "network"
        entries.append({
            "id": entry.get("id") or "",
            "concept": concept_id(entry.get("term") or "") if scope == "global" else "",
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
        hay = " ".join([
            str(item.get("name") or ""),
            str(item.get("caption") or ""),
            " ".join(str(t) for t in (item.get("tags") or [])),
            " ".join(str(t) for t in (item.get("concepts") or [])),
        ]).lower()
        if q in hay:
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
    if scope == "global":
        ensure_concept(term, kind="fandom" if kind == "fandom" else "meme", meaning=meaning, source="lexicon")
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
    valence = float(state.get("valence") or 0)
    arousal = float(state.get("arousal") or 0.5)
    intimacy = float(state.get("intimacy") or 0)
    emotion = state.get("emotion") or {}
    dims = {}
    if isinstance(emotion, dict):
        for key, value in list(emotion.items())[:7]:
            try:
                dims[str(key)] = round(float(value) * 100)
            except (TypeError, ValueError):
                continue
    dims.setdefault("心情值", round((valence + 1) * 50))
    dims.setdefault("亲密度", round(min(100, intimacy / 10)))
    dims.setdefault("唤醒", round(arousal * 100))
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
    return {
        "configured": bool(state),
        "owner": "九歌",
        "self": "大肥鱼",
        "inject_mode": "dsh-remembers",
        "auto_judge": True,
        "per_day": 0,
        "mood": round((valence + 1) * 50),
        "dims": dims,
        "reason": str(last_emotion.get("reason") or state.get("activity") or ""),
        "emotion_label": str(last_emotion.get("mood") or ""),
        "confidence": 50,
        "updated_at": state.get("last_interaction") or 0,
        "timeline": timeline,
        "active": state.get("mood") or "",
        "intimacy": intimacy,
        "stage": (state.get("stage") or {}).get("name", ""),
        "activity": state.get("activity", ""),
        "valence": valence,
        "arousal": arousal,
    }


STYLE_PROPOSAL = HOME / "persona-roles" / "state" / "style-proposal.json"
STYLE_BEGIN = "<!-- style:begin -->"
STYLE_END = "<!-- style:end -->"


def cmem_post(path: str, body: dict) -> dict:
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(CMEM_BASE + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def style_payload() -> dict:
    proposal = {}
    if STYLE_PROPOSAL.exists():
        proposal = read_json(STYLE_PROPOSAL)
    persona = cmem_get("/persona")
    constitution = str(persona.get("constitution") or "")
    current = ""
    match = re.search(re.escape(STYLE_BEGIN) + r"(.*?)" + re.escape(STYLE_END), constitution, re.S)
    if match:
        current = match.group(1).strip()
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
    if STYLE_BEGIN not in constitution or STYLE_END not in constitution:
        return {"ok": False, "error": "核心设定里没有 style 标记"}
    new_constitution = re.sub(
        re.escape(STYLE_BEGIN) + r".*?" + re.escape(STYLE_END),
        lambda _: STYLE_BEGIN + "\n" + style + "\n" + STYLE_END,
        constitution, count=1, flags=re.S)
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
    out = {"count": 0, "items": [], "persona_chars": 0}
    data = cmem_get("/memories?limit=100")
    if data:
        out["count"] = int(data.get("total") or 0)
        for item in data.get("items") or []:
            out["items"].append({
                "type": str(item.get("tier") or ""),
                "content": str(item.get("text") or ""),
                "time": item.get("ts") or "",
            })
        persona = cmem_get("/persona")
        chars = persona.get("chars") or {}
        out["persona_chars"] = int(chars.get("constitution") or 0) + int(chars.get("self_model") or 0)
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
    return {
        "notes": cmem_get("/notes") or [],
        "tasks": cmem_get("/tasks") or [],
        "diary": cmem_get("/diary") or [],
    }


def persona_payload() -> dict:
    persona = cmem_get("/persona")
    if not persona:
        return {"text": "(记忆服务未连接)", "sections": {}, "growth": "", "growth_chars": 0,
                "important": [], "proposals": {}, "synced": False, "history": [], "role": "大肥鱼",
                "agents_chars": 0}
    constitution = str(persona.get("constitution") or "")
    self_model = str(persona.get("self_model") or "")
    text = constitution
    if self_model:
        text += "\n\n## 自我认知\n\n" + self_model
    return {
        "text": text,
        "role": "大肥鱼",
        "sections": {"identity": constitution, "style": "", "relationship": ""},
        "growth": self_model,
        "growth_chars": len(self_model),
        "important": [],
        "proposals": {},
        "history": [],
        "synced": True,
        "agents_chars": len(text),
        "constitution": constitution,
        "self_model": self_model,
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
        if not text:
            return {"ok": False, "error": "自我认知不能为空"}
        if len(text) > 4000:
            return {"ok": False, "error": "自我认知最多 4000 字"}
        try:
            data = cmem_post("/persona/self", {"text": text})
            if data.get("ok") is False:
                return {"ok": False, "error": data.get("error") or "保存失败"}
            return {"ok": True, "field": field, "chars": len(text),
                    "self_model": data.get("self_model", text)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
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
        item["name"] = entry.get("name") or item["caption"] or Path(item["file"]).stem
        item["tags"] = entry.get("tags") if isinstance(entry.get("tags"), list) else []
        item["concepts"] = entry.get("concepts") if isinstance(entry.get("concepts"), list) else []
        item["usage_count"] = int(entry.get("usage_count") or 0)
    item_map = {item["file"]: item for item in items}
    user_items = [item_map[x["file"]] for x in user_items if x["file"] in item_map]
    items.sort(key=lambda x: (x["category"], str(x.get("name") or x["file"])))
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


def sticker_update_tags(rel: str, tags: list) -> dict:
    path, key = _sticker_file(rel)
    if path is None:
        return {"ok": False, "error": "文件不存在或路径不合法"}
    clean = []
    for tag in (tags if isinstance(tags, list) else [])[:30]:
        value = str(tag or "").strip()
        if value and len(value) <= 40 and value not in clean:
            clean.append(value)
    index = read_json(STICKERS / "index.json") or []
    if not isinstance(index, list):
        index = []
    entry = next((e for e in index if isinstance(e, dict) and str(e.get("file") or "").replace("\\", "/") == key), None)
    if entry is None:
        entry = {"file": key, "category": path.parent.name, "caption": "", "tags": []}
        index.append(entry)
    entry["tags"] = clean
    (STICKERS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "file": key, "tags": clean}


def sticker_update_concepts(rel: str, concepts: list) -> dict:
    path, key = _sticker_file(rel)
    if path is None:
        return {"ok": False, "error": "文件不存在或路径不合法"}
    ids = []
    for raw in (concepts if isinstance(concepts, list) else [])[:20]:
        term = str(raw or "").strip()
        if term.startswith("concept:"):
            term = term.split(":", 1)[1]
        if not term:
            continue
        entry = ensure_concept(term, kind="fandom", source="panel")
        cid = entry.get("id") or concept_id(term)
        if cid and cid not in ids:
            ids.append(cid)
    index = read_json(STICKERS / "index.json") or []
    if not isinstance(index, list):
        index = []
    entry = next((e for e in index if isinstance(e, dict) and str(e.get("file") or "").replace("\\", "/") == key), None)
    if entry is None:
        entry = {"file": key, "category": path.parent.name, "caption": "", "tags": []}
        index.append(entry)
    entry["concepts"] = ids
    (STICKERS / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "file": key, "concepts": ids}


def rolecard_payload() -> dict:
    import re

    card = ROLE_CARD.read_text(encoding="utf-8") if ROLE_CARD.exists() else ""
    match = re.search(r"<!-- persona-growth:begin -->(.*?)<!-- persona-growth:end -->", card, re.S)
    growth = match.group(1).strip() if match else ""
    sections = {}
    for name, begin, end in (
        ("identity", "<!-- persona-identity:begin -->", "<!-- persona-identity:end -->"),
        ("style", "<!-- persona-style:begin -->", "<!-- persona-style:end -->"),
        ("relationship", "<!-- persona-relationship:begin -->", "<!-- persona-relationship:end -->"),
    ):
        found = re.search(re.escape(begin) + r"(.*?)" + re.escape(end), card, re.S)
        sections[name] = found.group(1).strip() if found else ""
    style = sections.get("style", "")
    important = []
    important_match = re.search(r"<!-- persona-important:begin -->(.*?)<!-- persona-important:end -->", card, re.S)
    if important_match:
        important = [line[2:].strip() for line in important_match.group(1).splitlines() if line.strip().startswith("- ")]
    preamble = card.split("<!-- persona-identity:begin -->")[0].strip() if card else ""
    history = []
    if ROLE_HISTORY.is_dir():
        for item in sorted(ROLE_HISTORY.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if item.is_file():
                history.append({"name": item.name, "size": item.stat().st_size, "time": int(item.stat().st_mtime)})
    proposals = {}
    proposal_file = HOME / "persona-roles" / "state" / "section-proposals.json"
    if proposal_file.exists():
        try:
            data = json.loads(proposal_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                proposals = data
        except Exception:
            proposals = {}
    agents_text = AGENTS.read_text(encoding="utf-8") if AGENTS.exists() else ""
    return {
        "role": ROLE_CARD.stem,
        "card": card,
        "preamble": preamble,
        "sections": sections,
        "style": style,
        "important": important,
        "growth": growth,
        "growth_chars": len(growth),
        "history": history[:10],
        "synced": bool(growth) and growth in agents_text,
        "agents_chars": len(agents_text),
        "proposals": proposals,
    }


def sync_growth() -> dict:
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / "sync_growth.py")], capture_output=True, text=True, timeout=60)
    return {"ok": result.returncode == 0, "output": (result.stdout + result.stderr).strip()}


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
    return {"seen": seen[:40], "notes": notes[:20], "interests": interests[:10], "login": bili_payload()}


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
        "intimacy": mood.get("intimacy", 0),
        "stage": mood.get("stage", ""),
        "activity": mood.get("activity", ""),
        "proactive": (proactive_payload() or {}).get("enabled", False),
        "stickers_user": sum(1 for _ in STICKERS.rglob("u_*")) if STICKERS.is_dir() else 0,
        "bili_logged_in": bili_payload()["logged_in"],
        "memory_count": memory_payload()["count"],
    }
