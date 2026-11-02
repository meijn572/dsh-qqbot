"""Phase 4 autonomy 纯函数测试。"""
from __future__ import annotations

import unittest

from qqbot.domains.autonomy.bili import compose_share_text
from qqbot.domains.autonomy.state import similar_topic


class AutonomyTest(unittest.TestCase):
    def test_similar_topic(self) -> None:
        self.assertTrue(similar_topic("王者荣耀", "王者荣耀"))
        self.assertTrue(similar_topic("王者荣耀", "王者荣耀上分"))
        self.assertFalse(similar_topic("王者荣耀", "完全无关"))

    def test_compose_share_text(self) -> None:
        text = compose_share_text("这个视频挺有意思", ["BV1xx411c7mD"])
        self.assertIn("bilibili.com/video/BV1xx411c7mD", text)
        self.assertTrue(text.startswith("这个视频挺有意思"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
