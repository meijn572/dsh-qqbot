"""growth 任务共用的记忆证据块。"""
from __future__ import annotations

from qqbot.clients.memory import context_evidence
from settings import OWNER_CHAT_KEY


async def collect(l1: int, l3: int, l0: int) -> dict:
    """最近 L1/L3 + 它们引用的 L0（服务端已按 id/文本去重）。"""
    return await context_evidence({
        "tiers": ["L1", "L3"],
        "limits": {"L1": l1, "L3": l3},
        "scope": OWNER_CHAT_KEY,
        "l0_limit": l0,
    })


def format_block(ev: dict, l1_chars: int = 240, l3_chars: int = 400, l0_chars: int = 400,
                 max_chars: int = 16000) -> str:
    items = ev.get("items") or []
    l1_lines = []
    l3_lines = []
    for item in items:
        text = str(item.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        if str(item.get("tier")) == "L1":
            l1_lines.append(text[:l1_chars])
        elif str(item.get("tier")) == "L3":
            l3_lines.append(text[:l3_chars])

    l0_lines = []
    seen = set()
    for row in ev.get("l0") or []:
        text = str(row.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        digest = text[:200]
        if digest in seen:
            continue
        seen.add(digest)
        l0_lines.append(text[:l0_chars])

    if not l1_lines and not l3_lines and not l0_lines:
        return ""
    lines = ["【长期记忆】"]
    lines.extend(f"[L1] {x}" for x in l1_lines)
    lines.extend(f"[L3] {x}" for x in l3_lines)
    lines.append("【对应原话】")
    lines.extend(f"- {x}" for x in l0_lines)
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max(0, max_chars - 24)] + "\n…（证据过长已截断）"
    return text
