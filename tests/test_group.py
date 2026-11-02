"""Phase 4 group 纯函数测试。"""
from __future__ import annotations

import unittest

from qqbot.domains.group.slang import load_slang, network_meme_hint


class GroupTest(unittest.TestCase):
    def test_missing_slang(self) -> None:
        self.assertEqual(load_slang("__missing_group__"), [])

    def test_empty_meme(self) -> None:
        self.assertEqual(network_meme_hint(""), "")

    def test_no_match(self) -> None:
        self.assertEqual(network_meme_hint("完全不存在的词__"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
