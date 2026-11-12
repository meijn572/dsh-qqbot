"""Phase 4 autonomy 纯函数测试。"""
from __future__ import annotations

import unittest

from qqbot.domains.autonomy.bili import compose_share_text


class AutonomyTest(unittest.TestCase):
    def test_compose_share_text(self) -> None:
        text = compose_share_text("这个视频挺有意思", ["BV1xx411c7mD"])
        self.assertIn("bilibili.com/video/BV1xx411c7mD", text)
        self.assertTrue(text.startswith("这个视频挺有意思"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
