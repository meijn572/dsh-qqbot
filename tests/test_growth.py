"""Phase 3 growth 测试：只测纯格式/解析，不调 LLM。"""
from __future__ import annotations

import unittest

from qqbot.domains.growth.important import _items
from qqbot.domains.growth.style import _similar, style_block


class GrowthTest(unittest.TestCase):
    def test_style_block(self) -> None:
        text = "前面\n<!-- style:begin -->\n- 短句\n<!-- style:end -->\n后面"
        self.assertEqual(style_block(text), "- 短句")

    def test_style_block_missing(self) -> None:
        self.assertEqual(style_block("没有标记"), "")

    def test_similar(self) -> None:
        self.assertTrue(_similar("- 短句，结论在前", "- 短句，结论在前"))
        self.assertFalse(_similar("完全不一样", "另一段内容"))

    def test_important_items(self) -> None:
        text = "<!-- important:begin -->\n- 约定一\n- 约定二\n<!-- important:end -->"
        self.assertEqual(_items(text), ["约定一", "约定二"])

    def test_important_empty(self) -> None:
        self.assertEqual(_items("没有标记"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
