"""Phase 2 media 测试：不依赖 QQ / 外部视觉 API。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from qqbot.domains.media.download import download_images
from qqbot.domains.media.library import category_from_text, extract_note_keywords, should_hint
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

    def test_note_keywords(self) -> None:
        words = extract_note_keywords("把这张哭哭表情收进库里")
        self.assertIn("哭哭", words)

    def test_media_helpers_imported(self) -> None:
        self.assertEqual(category_from_text("开心"), "happy")
        self.assertTrue(should_hint("发个表情"))
        self.assertFalse(should_hint("今天吃什么"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
