"""图片预处理：统一成主模型/视觉接口能吃的格式。

不依赖 bridge 的全局状态；只处理本地文件。
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

log = logging.getLogger("qqbot.media.preprocess")


def vision_image(path: Path) -> tuple[str, bytes]:
    """动图抽 6 帧拼图；静态图统一转成视觉接口能吃的 JPEG/PNG。"""
    try:
        from PIL import Image

        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1) or 1
            fmt = (im.format or "").upper()
            if frames > 1:
                picks = [round(i * (frames - 1) / 5) for i in range(6)]
                cell = 220
                cols, rows = 3, 2
                sheet = Image.new("RGB", (cols * cell, rows * cell), (255, 255, 255))
                for index, frame_no in enumerate(picks):
                    im.seek(frame_no)
                    frame = im.convert("RGBA")
                    frame.thumbnail((cell - 10, cell - 10))
                    tile = Image.new("RGB", (cell, cell), (255, 255, 255))
                    tile.paste(frame, ((cell - frame.width) // 2, (cell - frame.height) // 2), frame)
                    sheet.paste(tile, ((index % cols) * cell, (index // cols) * cell))
                buf = io.BytesIO()
                sheet.save(buf, "JPEG", quality=85)
                return "jpeg", buf.getvalue()
            if fmt not in ("JPEG", "PNG"):
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=90)
                return "jpeg", buf.getvalue()
            return ("jpeg" if fmt == "JPEG" else "png"), path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        log.warning("图片预处理失败：%s", exc)
    raw = path.read_bytes()
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else ("gif" if suffix == "gif" else "png")
    return mime, raw


def native_image(path: Path) -> tuple[str, bytes]:
    """给 DSH 主模型的图片附件：动图拼帧，静态图过大时压到 1400px。"""
    mime, raw = vision_image(path)
    if len(raw) <= 2 * 1024 * 1024:
        return mime, raw
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            im.thumbnail((1400, 1400))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            return "jpeg", buf.getvalue()
    except Exception:  # noqa: BLE001
        return mime, raw
