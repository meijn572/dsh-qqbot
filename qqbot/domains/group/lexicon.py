"""统一梗/黑话/热词库。

kind 表示类型，scope 表示作用域，status 表示生命周期。
群黑话只是 scope=group:<id>，不再单独存文件。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from settings import DSH_HOME

LEXICON_FILE = DSH_HOME / "lexicon.json"
LEGACY_GROUP_DIR = DSH_HOME / "group-slang"
LEGACY_NETWORK_FILE = DSH_HOME / "network-memes.json"

KINDS = ("slang", "meme", "buzzword", "fandom", "abbreviation", "emoji", "event")
STATUSES = ("fresh", "hot", "stable", "archived")


def _clean(value: str, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def entry_id(term: str, scope: str) -> str:
    value = re.sub(r"\s+", "", _clean(term, 80))
    return f"lex:{scope}:{value}" if value else ""


def _normalize(entry: dict) -> dict:
    term = _clean(entry.get("term"), 80)
    scope = _clean(entry.get("scope") or "global", 80)
    kind = _clean(entry.get("kind") or ("slang" if scope.startswith("group:") else "meme"), 30)
    if kind not in KINDS:
        kind = "meme" if scope == "global" else "slang"
    status = _clean(entry.get("status") or "stable", 20)
    if status not in STATUSES:
        status = "stable"
    aliases = [str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()]
    return {
        "id": entry_id(term, scope),
        "term": term,
        "kind": kind,
        "scope": scope,
        "status": status,
        "meaning": _clean(entry.get("meaning")),
        "aliases": list(dict.fromkeys(aliases))[:20],
        "examples": [_clean(x, 200) for x in (entry.get("examples") or []) if str(x).strip()][:5],
        "count": int(entry.get("count") or 0),
        "first_seen": int(entry.get("first_seen") or 0),
        "last_seen": int(entry.get("last_seen") or 0),
        "source": _clean(entry.get("source"), 80),
    }


def _empty() -> dict:
    return {"version": 1, "legacy_imported": False, "entries": []}


def _legacy_entries() -> list[dict]:
    result: list[dict] = []
    if LEGACY_GROUP_DIR.is_dir():
        for path in sorted(LEGACY_GROUP_DIR.glob("*.json")):
            if path.stem == "state":
                continue
            try:
                items = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("term"):
                    continue
                result.append({
                    "term": item.get("term"),
                    "kind": "slang",
                    "scope": f"group:{path.stem}",
                    "status": "stable",
                    "meaning": item.get("meaning") or "",
                    "aliases": item.get("aliases") or [],
                    "examples": [item.get("example")] if item.get("example") else [],
                    "count": item.get("count") or 0,
                    "first_seen": item.get("first_seen") or item.get("last_seen") or 0,
                    "last_seen": item.get("last_seen") or 0,
                    "source": "group-log",
                })
    if LEGACY_NETWORK_FILE.exists():
        try:
            data = json.loads(LEGACY_NETWORK_FILE.read_text(encoding="utf-8"))
            items = data.get("entries") if isinstance(data, dict) else data
            for item in items or []:
                if not isinstance(item, dict) or not item.get("term"):
                    continue
                result.append({
                    "term": item.get("term"),
                    "kind": item.get("kind") or "meme",
                    "scope": item.get("scope") or "global",
                    "status": item.get("status") or "stable",
                    "meaning": item.get("meaning") or "",
                    "aliases": item.get("aliases") or [],
                    "examples": [item.get("example")] if item.get("example") else [],
                    "count": item.get("count") or 0,
                    "first_seen": item.get("first_seen") or item.get("last_seen") or 0,
                    "last_seen": item.get("last_seen") or 0,
                    "source": "network-memes",
                })
        except Exception:  # noqa: BLE001
            pass
    return result


def load_store() -> dict:
    if not LEXICON_FILE.exists():
        data = _empty()
        data["entries"] = [_normalize(x) for x in _legacy_entries()]
        data["legacy_imported"] = True
        save_store(data)
        return data
    try:
        data = json.loads(LEXICON_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = _empty()
    if not isinstance(data, dict):
        data = _empty()
    data.setdefault("version", 1)
    data.setdefault("entries", [])
    if not data.get("legacy_imported"):
        existing = {e.get("id") for e in data["entries"] if isinstance(e, dict)}
        for item in _legacy_entries():
            norm = _normalize(item)
            if norm["id"] and norm["id"] not in existing:
                data["entries"].append(norm)
        data["legacy_imported"] = True
        save_store(data)
    data["entries"] = [_normalize(e) for e in data["entries"] if isinstance(e, dict) and e.get("term")]
    return data


def save_store(data: dict) -> None:
    LEXICON_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEXICON_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LEXICON_FILE)


def list_entries(*, scope: str | None = None, kind: str | None = None,
                 status: str | None = None) -> list[dict]:
    entries = load_store().get("entries") or []
    if scope:
        entries = [e for e in entries if e.get("scope") == scope]
    if kind:
        entries = [e for e in entries if e.get("kind") == kind]
    if status:
        entries = [e for e in entries if e.get("status") == status]
    return sorted(entries, key=lambda e: (e.get("scope") or "", e.get("term") or ""))


def upsert_entry(term: str, *, kind: str, scope: str = "global", status: str = "stable",
                 meaning: str = "", aliases: list[str] | None = None,
                 examples: list[str] | None = None, source: str = "") -> dict:
    data = load_store()
    now = int(time.time())
    candidate = _normalize({
        "term": term, "kind": kind, "scope": scope, "status": status,
        "meaning": meaning, "aliases": aliases or [], "examples": examples or [],
        "first_seen": now, "last_seen": now, "source": source,
    })
    if not candidate["id"]:
        return {}
    for index, entry in enumerate(data["entries"]):
        if entry.get("id") != candidate["id"]:
            continue
        merged = dict(entry)
        merged.update({
            "term": candidate["term"],
            "kind": candidate["kind"],
            "scope": candidate["scope"],
            "status": candidate["status"],
            "last_seen": now,
        })
        if meaning:
            merged["meaning"] = candidate["meaning"]
        if aliases:
            merged["aliases"] = list(dict.fromkeys(list(merged.get("aliases") or []) + candidate["aliases"]))[:20]
        if examples:
            merged["examples"] = list(dict.fromkeys(list(merged.get("examples") or []) + candidate["examples"]))[:5]
        data["entries"][index] = _normalize(merged)
        save_store(data)
        return data["entries"][index]
    data["entries"].append(candidate)
    save_store(data)
    return candidate


def replace_scope(scope: str, items: list[dict], *, kind: str = "slang", source: str = "group-log") -> list[dict]:
    data = load_store()
    data["entries"] = [e for e in data["entries"] if e.get("scope") != scope]
    now = int(time.time())
    for item in items:
        if not isinstance(item, dict) or not item.get("term"):
            continue
        entry = _normalize({
            "term": item.get("term"),
            "kind": kind,
            "scope": scope,
            "status": item.get("status") or "stable",
            "meaning": item.get("meaning") or "",
            "aliases": item.get("aliases") or [],
            "examples": [item.get("example")] if item.get("example") else [],
            "count": item.get("count") or 0,
            "first_seen": item.get("first_seen") or item.get("last_seen") or now,
            "last_seen": item.get("last_seen") or now,
            "source": source,
        })
        data["entries"].append(entry)
    save_store(data)
    return [e for e in data["entries"] if e.get("scope") == scope]


def delete_entry(entry_id_value: str) -> bool:
    data = load_store()
    before = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if e.get("id") != entry_id_value]
    save_store(data)
    return len(data["entries"]) != before


def search_entries(query: str, *, scope: str | None = None, kind: str | None = None,
                   status: str | None = None) -> list[dict]:
    q = _clean(query, 80).lower()
    if not q:
        return []
    result = []
    for entry in list_entries(scope=scope, kind=kind, status=status):
        aliases = [str(a).lower() for a in (entry.get("aliases") or [])]
        hay = " ".join([str(entry.get("term") or ""), str(entry.get("meaning") or ""), *aliases]).lower()
        if q not in hay:
            continue
        score = 0
        if q == str(entry.get("term") or "").lower() or q in aliases:
            score += 100
        elif q in str(entry.get("term") or "").lower():
            score += 50
        if q in str(entry.get("meaning") or "").lower():
            score += 20
        result.append((score, entry))
    result.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in result]

LEXICON_REVIEW_PROMPT = """（内部词库维护，不要回复用户，不要调用工具。）

下面是最近 24 小时的私聊原文。

{text}

【本段命中的旧词】
{hits}

请判断两件事：
1. 对旧词有没有新的理解、修正或更具体的用法？没有就空。
2. 有没有出现新的梗/黑话/热词/缩写/角色称呼？没有就空。

例子：
旧词新解：
美女潘：群里给本人起的称呼，从「猛男潘」被当场改成「美女潘」，带自嘲和反串的调侃。
这次多了「必须是美女潘啊」这种接自嘲的用法。

新词：
奶蛋：黄色圆圆的，跟奶蛙一个系列。

只写这段里真的出现过的词。
新词必须有明确 meaning，拿不准就不写。
旧词没有新理解，不要为了有输出硬改。
普通词、语气词、地名、游戏名不算。
只返回 JSON：
{{"updates":[{{"term":"旧词","meaning":"新的解释","example":"原话"}}],
"new":[{{"term":"新词","meaning":"解释","kind":"meme","aliases":[],"example":"原话"}}]}}"""


def render_review_prompt(text: str, hits: list[str]) -> str:
    """词库复盘用的提示词。数据在外面取，模板留在这里。"""
    return LEXICON_REVIEW_PROMPT.format(
        text=text,
        hits="\n".join(hits) if hits else "（没有）",
    )
