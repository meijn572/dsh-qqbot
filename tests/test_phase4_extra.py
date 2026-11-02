"""Phase 4 group/qzone 纯函数测试。"""
from __future__ import annotations

import unittest

from qqbot.domains.group.proactive import _quiet, _strip_skip
from qqbot.domains.qzone.publish import text_ok


class Phase4Test(unittest.TestCase):
    def test_qzone_text_ok(self) -> None:
        self.assertTrue(text_ok("今天的云压得很低，像一块没拧干的抹布。"))
        self.assertFalse(text_ok("短"))
        self.assertFalse(text_ok("看这个 https://example.com"))
        self.assertFalse(text_ok("主人今天不在"))

    def test_quiet_hours(self) -> None:
        self.assertEqual(_quiet("0-8"), (0, 8))
        self.assertEqual(_quiet("bad"), (0, 8))

    def test_strip_skip(self) -> None:
        self.assertEqual(_strip_skip("SKIP"), "")
        self.assertEqual(_strip_skip("SKIP\n今天风大"), "今天风大")


if __name__ == "__main__":
    unittest.main(verbosity=2)
