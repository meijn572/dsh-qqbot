"""B 站推荐流、视频信息、兴趣与分享文案。"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

import aiohttp

from qqbot.domains.autonomy.state import (
    load_aut_state,
    load_interests,
    save_interests,
    similar_topic,
)
from settings import DSH_HOME

log = logging.getLogger("qqbot.autonomy.bili")
BILI_CRED = DSH_HOME / "bili-duty" / "bili_credential.json"
BILI_BUVID: dict[str, str] = {"b3": "", "b4": ""}
BILI_VIEW_CACHE: dict[str, dict] = {}


def apply_interest(topic: str, delta: float, evidence: str = "", source: str = "chat", memory_ids: list[str] | None = None) -> None:
    topic = re.sub(r"[\s。！？!?；;，,]+$", "", (topic or "").strip())[:24]
    if not topic:
        return
    items = load_interests()
    now = int(time.time())
    found = next((item for item in items if similar_topic(topic, str(item.get("topic", "")))), None)
    ids = [str(i) for i in (memory_ids or []) if i]
    if found is None:
        items.append({"topic": topic, "weight": round(max(1.0, delta), 2), "evidence": evidence[:80],
                      "source": source, "last_seen": now, "memory_ids": ids[:20]})
    else:
        if len(topic) >= 4 and len(topic) < len(str(found.get("topic", ""))):
            found["topic"] = topic
        found["weight"] = round(max(0.0, min(9.0, float(found.get("weight", 1)) + delta)), 2)
        found["last_seen"] = now
        if evidence:
            found["evidence"] = evidence[:80]
        if ids:
            found["memory_ids"] = list(dict.fromkeys([*(found.get("memory_ids") or []), *ids]))[-20:]
    items.sort(key=lambda x: float(x.get("weight", 0)), reverse=True)
    save_interests(items[:40])


def decay_interests() -> None:
    items = load_interests()
    now = int(time.time())
    changed = False
    for item in items:
        last = int(item.get("last_seen") or 0)
        if last and now - last > 3 * 86400:
            item["weight"] = round(float(item.get("weight", 0)) * 0.5, 2)
            item["last_seen"] = now
            changed = True
    if changed:
        save_interests([i for i in items if float(i.get("weight", 0)) > 0.3])


def pick_topic(cfg: dict) -> tuple[str, str]:
    items = load_interests()
    if not items:
        return "", "explore"
    state = load_aut_state()
    recent = {str(x) for x in (state.get("recent_topics") or [])[-2:]}
    pool = [i for i in items if str(i.get("topic", "")) not in recent] or items
    if random.random() >= float(cfg.get("free_explore_ratio", 0.4)):
        weights = [max(0.5, float(i.get("weight", 1))) ** 0.6 for i in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        return str(chosen.get("topic", "")), "interest"
    return "", "explore"


def compose_share_text(line: str, links: list[str]) -> str:
    text = (line or "").strip()
    normalized = []
    for item in links:
        value = str(item or "").strip()
        if not value:
            continue
        normalized.append(value if value.startswith("http") else f"https://www.bilibili.com/video/{value}")
    extra = [u for u in normalized if "bilibili.com" not in text]
    if extra:
        text += "\n\n" + "\n".join(extra[:2])
    return text


async def fetch_bili_feed(limit: int = 12) -> list[dict]:
    try:
        cred = json.loads(BILI_CRED.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    ua = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    b3 = cred.get("buvid3") or BILI_BUVID["b3"]
    b4 = cred.get("buvid4") or BILI_BUVID["b4"]
    try:
        async with aiohttp.ClientSession(headers=ua) as sess:
            if not b3:
                async with sess.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = (await resp.json()).get("data") or {}
                b3, b4 = str(data.get("b_3") or ""), str(data.get("b_4") or "")
                BILI_BUVID.update({"b3": b3, "b4": b4})
                try:
                    cred["buvid3"], cred["buvid4"] = b3, b4
                    BILI_CRED.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            cookie = (
                f"SESSDATA={cred.get('sessdata', '')}; bili_jct={cred.get('bili_jct', '')}; "
                f"DedeUserID={cred.get('dedeuserid', '')}; buvid3={b3}; buvid4={b4}"
            )
            url = f"https://api.bilibili.com/x/web-interface/index/top/rcmd?fresh_type=3&ps={max(1, min(limit, 20))}"
            async with sess.get(url, headers={"Cookie": cookie}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                payload = await resp.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        log.warning("推荐流获取失败: %s", exc)
        return []
    if payload.get("code") != 0:
        log.warning("推荐流返回 code=%s msg=%s", payload.get("code"), payload.get("message"))
        return []
    items = (payload.get("data") or {}).get("item") or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "bvid": str(item.get("bvid") or ""),
            "title": str(item.get("title") or ""),
            "up": str((item.get("owner") or {}).get("name") or ""),
        })
    return [i for i in out if i["bvid"]]


async def fetch_bili_view(bvid: str) -> dict | None:
    if bvid in BILI_VIEW_CACHE:
        return BILI_VIEW_CACHE[bvid]
    ua = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
    try:
        async with aiohttp.ClientSession(headers=ua) as sess:
            async with sess.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": bvid},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                payload = await resp.json(content_type=None)
    except Exception:  # noqa: BLE001
        return None
    if payload.get("code") != 0:
        return None
    data = payload.get("data") or {}
    info = {
        "bvid": bvid,
        "title": str(data.get("title") or "")[:80],
        "up": str((data.get("owner") or {}).get("name") or "")[:40],
        "duration": int(data.get("duration") or 0),
    }
    BILI_VIEW_CACHE[bvid] = info
    return info
