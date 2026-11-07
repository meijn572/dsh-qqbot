"""来源里没有主人时，不要把模型补出来的主人留下。"""
import os
import sys
import unittest

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "..", "service")
sys.path.insert(0, SERVICE_DIR)

from service.extractor import _guard_master


class SubjectGuardTest(unittest.TestCase):
    def test_guard_when_source_has_only_me(self):
        rows = [{"text": "我：看了个视频"}]
        self.assertEqual(_guard_master("主人看了个视频", rows), "我看了个视频")

    def test_do_not_touch_when_source_mentions_master(self):
        rows = [{"text": "主人：我今天好累"}]
        self.assertEqual(_guard_master("主人说今天好累", rows), "主人说今天好累")

    def test_no_rows_keeps_text(self):
        self.assertEqual(_guard_master("主人看了个视频", None), "主人看了个视频")


if __name__ == "__main__":
    unittest.main()
