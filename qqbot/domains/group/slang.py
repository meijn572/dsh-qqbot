"""群日志与黑话兼容层。

存储已经统一到 lexicon.py；这个模块只保留 bridge 需要的旧接口。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from settings import DSH_HOME
from qqbot.domains.group.lexicon import list_entries, replace_scope, search_entries

log = logging.getLogger("qqbot.group.slang")
GROUP_SLANG_DIR = DSH_HOME / "group-slang"  # 仅保留旧状态文件路径
GROUP_LOG_DIR = DSH_HOME / "group-log"


def log_group_message(chat_key: str, user_id: int, text: str) -> None:
    if not text or not chat_key.startswith("group:"):
        return
    try:
        gid = chat_key.split(":", 1)[1]
        GROUP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = GROUP_LOG_DIR / f"{gid}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": int(time.time()), "user": str(user_id), "text": text[:300]}, ensure_ascii=False) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 600:
            path.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("group log failed: %s", exc)


def _legacy_shape(entry: dict) -> dict:
    examples = entry.get("examples") or []
    return {
        "term": entry.get("term") or "",
        "meaning": entry.get("meaning") or "",
        "example": examples[0] if examples else "",
        "aliases": entry.get("aliases") or [],
        "count": int(entry.get("count") or 0),
        "first_seen": int(entry.get("first_seen") or 0),
        "last_seen": int(entry.get("last_seen") or 0),
    }


def load_slang(gid: str) -> list[dict]:
    return [_legacy_shape(e) for e in list_entries(scope=f"group:{gid}")]


def save_slang(gid: str, items: list[dict]) -> None:
    replace_scope(f"group:{gid}", items, kind="slang", source="group-log")


def load_network_memes() -> list[dict]:
    return [_legacy_shape(e) for e in list_entries(scope="global")]


def network_meme_hint(text: str) -> str:
    text = text or ""
    if not text:
        return ""
    hits = []
    for entry in search_entries(text, scope="global"):
        # search_entries 是子串搜索；这里再按 term/alias 精确确认
        terms = [str(entry.get("term") or ""), *[str(a) for a in (entry.get("aliases") or [])]]
        matched = next((term for term in terms if len(term) >= 2 and term in text), "")
        if not matched:
            continue
        meaning = str(entry.get("meaning") or "").strip()
        hits.append(f"{matched}→{meaning[:120]}" if meaning else matched)
        if len(hits) >= 4:
            break
    if not hits:
        return ""
    return "（网络梗：" + "；".join(hits) + "。按语境自然理解，别逐条解释。）"
