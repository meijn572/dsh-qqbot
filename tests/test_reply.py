"""回复/媒体桥接函数的导入回归：防止重构后 NameError。"""
from __future__ import annotations

import unittest

from bridge import category_from_text, sanitize_markdown, should_hint, split_bubbles


class ReplyTest(unittest.TestCase):
    def test_sanitize_markdown(self) -> None:
        self.assertEqual(sanitize_markdown("**你好**\n[链接](https://example.com)"), "你好\n链接 https://example.com")

    def test_split_bubbles(self) -> None:
        self.assertEqual(split_bubbles("短句"), ["短句"])
        self.assertGreaterEqual(len(split_bubbles("第一句。第二句！第三句？")), 1)

    def test_media_helpers(self) -> None:
        self.assertEqual(category_from_text("开心"), "happy")
        self.assertTrue(should_hint("发个表情"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
