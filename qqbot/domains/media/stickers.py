"""表情包收藏：分类、去重、落库。"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

from qqbot.domains.media.library import (
    MEME_DIR,
    find_existing_sticker,
    find_signature_match,
    index_add,
    is_sticker_path,
    remember_sticker_info,
    remember_sticker_meta,
    sticker_signature,
)
from qqbot.domains.media.vision import classify_sticker, describe_sticker

log = logging.getLogger("qqbot.media.stickers")


async def collect_sticker(source: Path, override: str | None = None, note: str = "") -> str | None:
    """分类并落库，返回类别名。override 优先（用户明确说了类别）。"""
    if source.stat().st_size > 8 * 1024 * 1024:
        return None
    raw = source.read_bytes()
    suffix = source.suffix.lower() or ".jpg"
    try:
        from PIL import Image

        with Image.open(source) as im:
            frames = getattr(im, "n_frames", 1) or 1
            fmt = (im.format or "").upper()
            if frames > 1:
                suffix = ".gif"
            elif fmt not in ("JPEG", "PNG"):
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=90)
                raw = buf.getvalue()
                suffix = ".jpg"
    except Exception:  # noqa: BLE001
        pass
    digest = hashlib.sha256(raw).hexdigest()[:16]
    filename = f"u_{digest}{suffix}"
    existing = find_existing_sticker(filename)
    if existing is not None:
        rel = str(existing.relative_to(MEME_DIR))
        category = existing.parent.name
        index_add(rel, category, "")
        remember_sticker_info(source, rel)
        remember_sticker_meta(source, rel)
        log.info("表情包已存在，更新索引：%s", rel)
        return category
    sig = sticker_signature(source)
    near = find_signature_match(sig)
    if near:
        category = (MEME_DIR / near).parent.name
        index_add(near, category, "")
        remember_sticker_info(source, near)
        remember_sticker_meta(source, near)
        log.info("表情包近似重复，合并到：%s", near)
        return category
    info = await describe_sticker(source)
    category = override or info.get("category") or await classify_sticker(source)
    folder = MEME_DIR / category
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    target.write_bytes(raw)
    log.info("收藏表情包 -> %s (%s)", target.name, category)
    index_add(
        str(target.relative_to(MEME_DIR)),
        category,
        info.get("caption", ""),
        identity=info.get("identity") or [],
        action=info.get("action") or [],
        expression=info.get("expression") or [],
        generic=info.get("generic") or [],
        sig=sig,
    )
    remember_sticker_info(source, str(target.relative_to(MEME_DIR)))
    remember_sticker_meta(source, str(target.relative_to(MEME_DIR)))
    return category
