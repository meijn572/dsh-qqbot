"""气泡切分：按她自己写的换行走。"""
from __future__ import annotations

import unittest

from bridge import split_bubbles


class BubbleSplitTest(unittest.TestCase):
    def test_two_paragraphs(self) -> None:
        out = split_bubbles("第一段说完了。\n\n第二段接着说。")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], "第一段说完了。")
        self.assertEqual(out[1], "第二段接着说。")

    def test_short_paragraphs_stay_separate(self) -> None:
        out = split_bubbles("好。\n\n行吧。\n\n那就这样。")
        self.assertEqual(out, ["好。", "行吧。", "那就这样。"])

    def test_single_paragraph_not_split(self) -> None:
        text = "第一句。第二句。第三句。"
        self.assertEqual(split_bubbles(text), [text])

    def test_merge_when_over_limit(self) -> None:
        text = "\n\n".join(f"第{i}段。" for i in range(1, 7))
        out = split_bubbles(text)
        self.assertEqual(len(out), 3)
        self.assertIn("\n\n", out[0])

    def test_long_paragraph_split(self) -> None:
        text = "说了很多事情，" * 40 + "收尾。"
        out = split_bubbles(text)
        self.assertGreater(len(out), 1)
        for bubble in out:
            self.assertLessEqual(len(bubble), 210)

    def test_empty(self) -> None:
        self.assertEqual(split_bubbles("   "), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
