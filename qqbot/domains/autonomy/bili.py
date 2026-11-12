"""B 站推荐流、视频信息、兴趣与分享文案。"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

import aiohttp


from settings import DSH_HOME

log = logging.getLogger("qqbot.autonomy.bili")
BILI_CRED = DSH_HOME / "bili-duty" / "bili_credential.json"
BILI_BUVID: dict[str, str] = {"b3": "", "b4": ""}
BILI_VIEW_CACHE: dict[str, dict] = {}


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
