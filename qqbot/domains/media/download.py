"""下载 OneBot 图片/表情到本地 inbox，并记录 IMAGE_META。"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Callable

import aiohttp

log = logging.getLogger("qqbot.media.download")


async def download_images(
    event: dict,
    inbox: Path,
    image_meta: dict[str, dict],
    local_path: Callable[[str], Path | None],
) -> list[str]:
    paths: list[str] = []
    for seg in event.get("message") or []:
        seg_type = str(seg.get("type") or "")
        if seg_type not in ("image", "mface"):
            continue
        data = seg.get("data") or {}
        emoji_id = str(data.get("emoji_id") or data.get("emojiId") or "")
        key = str(data.get("key") or data.get("emoji_key") or data.get("emojiKey") or "")
        package_id = str(data.get("emoji_package_id") or data.get("emojiPackageId") or "")
        summary = str(data.get("summary") or data.get("text") or "")
        try:
            sub_type = int(data.get("sub_type") or 0)
        except (TypeError, ValueError):
            sub_type = 0
        sticker = seg_type == "mface" or bool(emoji_id or key) or sub_type == 1 or "表情" in summary
        url = str(data.get("url") or data.get("file") or "")
        local = local_path(str(data.get("file") or ""))
        if url.startswith("http"):
            try:
                inbox.mkdir(parents=True, exist_ok=True)
                path = inbox / f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}.jpg"
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                        if r.status == 200:
                            path.write_bytes(await r.read())
                            local = path
            except Exception as exc:  # noqa: BLE001
                log.warning("image download failed: %s", exc)
        if local is not None and local.is_file():
            image_meta[str(local)] = {
                "sticker": sticker,
                "emoji_id": emoji_id,
                "emoji_package_id": package_id,
                "key": key,
                "summary": summary or ("[动画表情]" if sticker else "[图片]"),
                "sub_type": 1 if sticker else sub_type,
            }
            paths.append(str(local))
    return paths
