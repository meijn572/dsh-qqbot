"""Phase 2 media 测试：不依赖 QQ / 外部视觉 API。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from qqbot.domains.media.download import download_images
from qqbot.domains.media.library import (
    _score_entry,
    category_from_text,
    clean_facets,
    clean_label,
    should_hint,
)
from qqbot.domains.media.preprocess import native_image, vision_image


class MediaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_static_image_preprocess(self) -> None:
        path = self.root / "a.jpg"
        Image.new("RGB", (320, 200), (200, 100, 50)).save(path, "JPEG")
        mime, raw = vision_image(path)
        self.assertEqual(mime, "jpeg")
        self.assertGreater(len(raw), 0)

    def test_gif_contact_sheet(self) -> None:
        path = self.root / "a.gif"
        frames = [Image.new("RGB", (80, 80), color) for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
        mime, raw = vision_image(path)
        self.assertEqual(mime, "jpeg")
        self.assertGreater(len(raw), 1000)

    def test_native_image_downscales_large(self) -> None:
        path = self.root / "big.jpg"
        Image.effect_noise((2200, 2200), 80).convert("RGB").save(path, "JPEG", quality=100)
        _, raw = native_image(path)
        self.assertLessEqual(len(raw), 2 * 1024 * 1024 + 1024)

    def test_download_local_image(self) -> None:
        path = self.root / "in.jpg"
        Image.new("RGB", (32, 32), (1, 2, 3)).save(path, "JPEG")
        event = {"message": [{"type": "image", "data": {"file": str(path), "summary": "[图片]"}}]}
        meta: dict[str, dict] = {}
        paths = __import__("asyncio").run(
            download_images(event, self.root / "inbox", meta, lambda raw: Path(raw) if Path(raw).is_file() else None)
        )
        self.assertEqual(paths, [str(path)])
        self.assertFalse(meta[str(path)]["sticker"])
        self.assertEqual(meta[str(path)]["summary"], "[图片]")

    def test_media_helpers_imported(self) -> None:
        self.assertEqual(category_from_text("开心"), "happy")
        self.assertTrue(should_hint("发个表情"))
        self.assertFalse(should_hint("今天吃什么"))

    def test_label_is_validated_not_generated(self) -> None:
        self.assertEqual(clean_label("大笑奶龙"), "大笑奶龙")
        self.assertEqual(clean_label("这是，标点"), "")
        self.assertEqual(clean_label("一" * 13), "")

    def test_facets_are_clean_and_weighted(self) -> None:
        self.assertEqual(clean_facets("奶龙, 小恐龙，奶龙"), ["奶龙", "小恐龙"])
        entry = {
            "label": "大笑奶龙",
            "identity": ["奶龙"],
            "expression": ["大笑"],
            "generic": ["搞笑"],
        }
        self.assertGreater(_score_entry(entry, "奶龙"), _score_entry(entry, "搞笑"))

    def test_caption_is_only_fallback(self) -> None:
        entry = {
            "label": "奶龙举旗",
            "identity": ["奶龙"],
            "caption": "举着一面小旗子",
        }
        self.assertIsNotNone(_score_entry(entry, "奶龙"))
        self.assertEqual(_score_entry(entry, "小旗子"), 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
