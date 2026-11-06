"""把模型给的原话 evidence 映射回记忆 id。

模型只指认原话，不接触数据库 id。
"""
from __future__ import annotations

import difflib
import re

_PUNCT = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’（）()\[\]【】…—\-]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", str(text or "")).lower()


def _best_coverage(evidence: str, source: str) -> float:
    """evidence 的一小段在 source 里最长能连续覆盖多少。"""
    ev = normalize(evidence)
    src = normalize(source)
    if not ev or not src:
        return 0.0
    if ev in src:
        return 1.0
    if len(ev) < 4:
        return 0.0
    matcher = difflib.SequenceMatcher(None, ev, src, autojunk=False)
    match = matcher.find_longest_match(0, len(ev), 0, len(src))
    return match.size / len(ev)


def match_evidence(evidence: list[str], rows: list[dict], threshold: float = 0.85) -> tuple[list[int], str]:
    """返回 (source_ids, source_status)。

    rows: [{"id": int, "text": str}, ...]
    """
    quotes = [str(x or "").strip() for x in (evidence or []) if str(x or "").strip()]
    if not quotes or not rows:
        return [], "unverified"
    ids: list[int] = []
    for quote in quotes:
        hits: list[tuple[float, int]] = []
        for row in rows:
            score = _best_coverage(quote, str(row.get("text") or ""))
            if score >= threshold:
                hits.append((score, int(row.get("id") or 0)))
        if not hits:
            continue
        best = max(score for score, _ in hits)
        for score, mid in hits:
            if score >= best - 0.001 and mid and mid not in ids:
                ids.append(mid)
    if not ids:
        return [], "unverified"
    return ids, "verified"
