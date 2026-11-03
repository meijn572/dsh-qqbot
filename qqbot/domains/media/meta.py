"""表情语义引用：把 source/file/query 解析成库内表情，并写回索引。

bridge 只负责队列和时机；这里负责“这张到底是谁、要写什么”。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from qqbot.domains.media.library import (
    MEME_DIR,
    find_by_keyword,
    find_signature_match,
    index_add,
    sticker_signature,
)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(MEME_DIR.resolve())).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return ""


def _source_rel(source: str) -> str:
    raw = str(source or "").strip()
    if not raw:
        return ""
    path = Path(raw)
    current = _rel(path)
    if current:
        return current
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""
    matches = sorted(MEME_DIR.rglob(f"u_{digest}*"))
    if matches:
        return _rel(matches[0])
    # 同图被重新压缩/转格式时 hash 不同，但收藏阶段会按感知 hash 合并
    near = find_signature_match(sticker_signature(path))
    return _file_rel(near) if near else ""


def _file_rel(target: str) -> str:
    raw = str(target or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or ".." in raw.split("/"):
        return ""
    path = (MEME_DIR / raw).resolve()
    if MEME_DIR.resolve() not in path.parents or not path.is_file():
        return ""
    return raw


def _query_rel(query: str) -> str:
    path = find_by_keyword(query)
    return _rel(Path(path)) if path else ""


def resolve_ref(ref: str) -> str:
    """source:/file:/query: → 库内相对路径；解析不到返回空串。"""
    value = str(ref or "").strip()
    if not value:
        return ""
    kind, sep, target = value.partition(":")
    if not sep:
        return _source_rel(value)
    kind = kind.lower()
    if kind == "source":
        return _source_rel(target)
    if kind == "file":
        return _file_rel(target)
    if kind == "query":
        return _query_rel(target)
    return ""


def apply_record(record: dict) -> dict:
    """应用一条主模型语义记录；source 未落盘时返回 pending，让 bridge 稍后重试。"""
    ref = str(record.get("ref") or record.get("source") or "").strip()
    rel = resolve_ref(ref)
    if not rel:
        return {"ok": False, "pending": ref.startswith("source:") or bool(record.get("source"))}
    tags = record.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,，、\s]+", tags) if t.strip()]
    index_add(
        rel,
        Path(rel).parent.name,
        str(record.get("caption") or ""),
        list(tags)[:12],
        name=str(record.get("name") or ""),
    )
    return {"ok": True, "rel": rel}
