"""自主刷状态：兴趣、已看、运行状态。"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from settings import CONFIG, DSH_HOME

log = logging.getLogger("qqbot.autonomy.state")
BILI_AUTONOMY_DIR = DSH_HOME / "bili-autonomy"
AUT_INTERESTS = BILI_AUTONOMY_DIR / "interests.json"
AUT_STATE = BILI_AUTONOMY_DIR / "state.json"
AUT_REPORT_DIR = BILI_AUTONOMY_DIR / "out"
AUT_SEEN = BILI_AUTONOMY_DIR / "seen.json"


def autonomy_cfg() -> dict:
    merged = {
        "enabled": True,
        "min_gap_minutes": 45,
        "daily_max": 10,
        "quiet_hours": "0-8",
        "free_explore_ratio": 0.25,
        "max_videos_per_round": 3,
        "share_max_per_day": 3,
    }
    merged.update(CONFIG.get("bili_autonomy") or {})
    return merged


def load_interests() -> list[dict]:
    if not AUT_INTERESTS.exists():
        return []
    try:
        data = json.loads(AUT_INTERESTS.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_interests(items: list[dict]) -> None:
    AUT_INTERESTS.parent.mkdir(parents=True, exist_ok=True)
    AUT_INTERESTS.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def load_aut_seen() -> list[dict]:
    if not AUT_SEEN.exists():
        return []
    try:
        data = json.loads(AUT_SEEN.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def aut_seen_set() -> set[str]:
    return {str(i.get("bvid")) for i in load_aut_seen() if i.get("bvid")}


def mark_aut_seen(videos: list[dict], topic: str) -> None:
    items = load_aut_seen()
    known = aut_seen_set()
    now = int(time.time())
    for video in videos:
        bvid = str(video.get("bvid") or "").strip()
        if not bvid or bvid in known:
            continue
        items.append({"bvid": bvid, "title": str(video.get("title") or "")[:80], "topic": topic, "ts": now})
        known.add(bvid)
    save = items[-300:]
    AUT_SEEN.parent.mkdir(parents=True, exist_ok=True)
    AUT_SEEN.write_text(json.dumps(save, ensure_ascii=False, indent=1), encoding="utf-8")


def load_aut_state() -> dict:
    if not AUT_STATE.exists():
        return {"date": "", "rounds": 0, "shares": 0, "last_run": 0, "last_extract": 0}
    try:
        data = json.loads(AUT_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {}
    base = {"date": "", "rounds": 0, "shares": 0, "last_run": 0, "last_extract": 0}
    base.update(data or {})
    return base


def save_aut_state(state: dict) -> None:
    AUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    AUT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def similar_topic(a: str, b: str) -> bool:
    def clean(text: str) -> str:
        return re.sub(r"[\s，。；;、!?！？~]+", "", str(text or ""))

    a, b = clean(a), clean(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True

    def bigrams(text: str) -> set[str]:
        return {text[i:i + 2] for i in range(len(text) - 1)}

    left, right = bigrams(a), bigrams(b)
    if left and right and len(left & right) / len(left | right) >= 0.6:
        return True
    english = {t.lower() for t in re.findall(r"[A-Za-z]{3,}", a)}
    other = {t.lower() for t in re.findall(r"[A-Za-z]{3,}", b)}
    return bool(english & other)


def read_new_l1(after_rowid: int = 0, limit: int = 12) -> tuple[list[tuple], int]:
    """读记忆服务新增的 L1 原子记忆（按 id 递增）。"""
    import json as _json
    import urllib.request as _url
    from settings import CMEM_BASE

    try:
        url = f"{CMEM_BASE}/memories?tier=L1&limit=200"
        with _url.urlopen(url, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("读 L1 失败：%s", exc)
        return [], after_rowid
    items = sorted(data.get("items") or [], key=lambda x: int(x.get("id") or 0))
    rows = []
    for item in items:
        mid = int(item.get("id") or 0)
        if mid <= int(after_rowid):
            continue
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(item.get("ts") or 0)))
        rows.append((mid, f"svc:{mid}", str(item.get("text") or ""), "L1", ts))
    rows = rows[:max(1, int(limit))]
    top = max((int(r[0]) for r in rows), default=int(after_rowid))
    return rows, top
