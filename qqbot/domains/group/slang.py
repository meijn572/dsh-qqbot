"""群日志与黑话/网络梗存储。"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from settings import DSH_HOME

log = logging.getLogger("qqbot.group.slang")
GROUP_SLANG_DIR = DSH_HOME / "group-slang"
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


def load_slang(gid: str) -> list[dict]:
    path = GROUP_SLANG_DIR / f"{gid}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or []
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_slang(gid: str, items: list[dict]) -> None:
    GROUP_SLANG_DIR.mkdir(parents=True, exist_ok=True)
    (GROUP_SLANG_DIR / f"{gid}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


NETWORK_MEMES_FILE = DSH_HOME / "network-memes.json"


def load_network_memes() -> list[dict]:
    try:
        data = json.loads(NETWORK_MEMES_FILE.read_text(encoding="utf-8"))
        items = data.get("entries") if isinstance(data, dict) else data
        return [item for item in (items or []) if isinstance(item, dict) and item.get("term")]
    except Exception:  # noqa: BLE001
        return []


def save_network_memes(items: list[dict]) -> None:
    NETWORK_MEMES_FILE.write_text(
        json.dumps({"entries": items}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def network_meme_hint(text: str) -> str:
    text = text or ""
    if not text:
        return ""
    hits = []
    for item in load_network_memes():
        term = str(item.get("term") or "").strip()
        if len(term) < 2 or term not in text:
            continue
        meaning = str(item.get("meaning") or "").strip()
        hits.append(f"{term}→{meaning[:120]}" if meaning else term)
        if len(hits) >= 4:
            break
    if not hits:
        return ""
    return "（网络梗：" + "；".join(hits) + "。按语境自然理解，别逐条解释。）"
