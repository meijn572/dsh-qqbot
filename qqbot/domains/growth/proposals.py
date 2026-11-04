"""人格复盘候选的纯文件存储。

不依赖 aiohttp；面板、复盘流程和工具都可以安全导入。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from settings import DSH_HOME

STATE = DSH_HOME / "persona-roles" / "state" / "review-state.json"
PROPOSALS = DSH_HOME / "persona-roles" / "state" / "review-proposals.json"
TARGETS = ("judgment", "relationship", "commitment")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_state() -> dict:
    return _load(STATE, {})


def save_state(state: dict) -> None:
    _save(STATE, state)


def load_proposals() -> list[dict]:
    data = _load(PROPOSALS, {"items": []})
    return data.get("items") if isinstance(data, dict) and isinstance(data.get("items"), list) else []


def save_proposals(items: list[dict]) -> None:
    _save(PROPOSALS, {"version": 1, "items": items})


def _new_id(target: str) -> str:
    return f"{target}-{int(time.time() * 1000)}"


def add_proposals(target: str, ops: list[dict], reason: str, evidence: list[str] | None = None) -> list[dict]:
    if target not in TARGETS:
        raise ValueError("未知复盘目标")
    if not ops:
        return []
    items = load_proposals()
    added = []
    for op in ops[:3]:
        text = str(op.get("text") or "").strip()
        if not text:
            continue
        item = {
            "id": _new_id(target),
            "target": target,
            "ops": [{
                "op": str(op.get("op") or "add"),
                "text": text[:300],
                **({"from": str(op.get("from") or "")[:300]} if op.get("from") else {}),
                **({"reason": str(op.get("reason") or reason or "")[:200]} if (op.get("reason") or reason) else {}),
            }],
            "reason": str(reason or "")[:300],
            "evidence": (evidence or [])[:8],
            "created_at": int(time.time()),
            "status": "pending",
        }
        items.append(item)
        added.append(item)
    save_proposals(items[-200:])
    return added


def add_commitment(item: str, reason: str = "", evidence: list[str] | None = None) -> dict | None:
    text = str(item or "").strip()[:100]
    if not text:
        return None
    items = load_proposals()
    if any(x.get("target") == "commitment" and x.get("status") == "pending"
           and x.get("ops", [{}])[0].get("text") == text for x in items):
        return None
    proposal = {
        "id": _new_id("commitment"),
        "target": "commitment",
        "ops": [{"op": "add", "text": text, "reason": str(reason or "")[:200]}],
        "reason": str(reason or "")[:300],
        "evidence": (evidence or [])[:8],
        "created_at": int(time.time()),
        "status": "pending",
    }
    items.append(proposal)
    save_proposals(items[-200:])
    return proposal


def pending() -> list[dict]:
    return [x for x in load_proposals() if x.get("status") == "pending"]


def set_status(proposal_id: str, status: str) -> bool:
    items = load_proposals()
    for item in items:
        if item.get("id") == proposal_id:
            item["status"] = status
            item["updated_at"] = int(time.time())
            save_proposals(items)
            return True
    return False


def recent_history(days: int = 30, per_target: int = 5) -> str:
    cutoff = time.time() - max(1, days) * 86400
    lines = []
    for target in TARGETS:
        seen = [
            x for x in load_proposals()
            if x.get("target") == target and float(x.get("created_at") or 0) >= cutoff
        ][-per_target:]
        for item in seen:
            op = (item.get("ops") or [{}])[0]
            text = str(op.get("text") or "")[:120]
            lines.append(f"[{target}][{item.get('status')}] {op.get('op')} {text}")
    return "\n".join(lines) or "（没有历史候选）"
