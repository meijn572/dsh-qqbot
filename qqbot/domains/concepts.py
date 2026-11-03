"""跨 lexicon / 表情 / 记忆的轻量概念引用。

只做“明确的 concept”，不做自动实体识别。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from settings import DSH_HOME

CONCEPTS_FILE = DSH_HOME / "concepts.json"


def concept_id(term: str) -> str:
    value = re.sub(r"\s+", "", str(term or "").strip())
    if value.startswith("concept:"):
        value = value.split(":", 1)[1]
    return f"concept:{value}" if value else ""


def load_concepts() -> dict:
    try:
        data = json.loads(CONCEPTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_concepts(data: dict) -> None:
    CONCEPTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def ensure_concept(
    term: str,
    *,
    kind: str = "term",
    scope: str = "global",
    status: str = "stable",
    meaning: str = "",
    source: str = "",
) -> dict:
    term = str(term or "").strip()
    if term.startswith("concept:"):
        term = term.split(":", 1)[1]
    cid = concept_id(term)
    if not cid:
        return {}
    data = load_concepts()
    entry = data.get(cid) if isinstance(data.get(cid), dict) else {}
    now = int(time.time())
    entry.update({
        "id": cid,
        "term": str(term).strip(),
        "kind": entry.get("kind") or kind,
        "scope": entry.get("scope") or scope,
        "status": entry.get("status") or status,
        "first_seen": entry.get("first_seen") or now,
        "last_seen": now,
    })
    if meaning and not entry.get("meaning"):
        entry["meaning"] = str(meaning)[:300]
    if source:
        sources = list(entry.get("sources") or [])
        if source not in sources:
            sources.append(source)
        entry["sources"] = sources
    data[cid] = entry
    save_concepts(data)
    return entry


def get_concept(cid: str) -> dict:
    data = load_concepts()
    entry = data.get(str(cid or ""))
    return entry if isinstance(entry, dict) else {}


def concepts_for_terms(terms: list[str], *, kind: str = "term", source: str = "") -> list[str]:
    result: list[str] = []
    for term in terms:
        entry = ensure_concept(term, kind=kind, source=source)
        cid = entry.get("id")
        if cid and cid not in result:
            result.append(cid)
    return result
