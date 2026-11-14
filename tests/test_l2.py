"""L1 只收确定事实；L2 到期自动标记（复查流程已删）。"""
import os
import sys
import tempfile
import time
import unittest

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "..", "service")
sys.path.insert(0, SERVICE_DIR)

from service import memory_core as mc
from service.extractor import _is_speculation


class L2StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mc.MemoryStore(os.path.join(self.tmp.name, "m.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _add(self, text, **kw):
        return self.store.add(mc.MemoryInput(
            text=text, tier="L2", l2_status="hypothesis",
            confidence=kw.pop("confidence", 0.6),
            expires_at=kw.pop("expires_at", time.time() + 86400),
            **kw,
        ))

    def test_l1_rejects_speculation(self):
        self.assertTrue(_is_speculation("他可能最近不想吃辣"))
        self.assertTrue(_is_speculation("我猜他今天很累"))
        self.assertFalse(_is_speculation("主人说今天很累"))

    def test_l2_expire_marks_old_rows(self):
        """复查已删，只剩过期标记：到期自动转 expired。"""
        mid = self._add("他可能最近不想吃辣")
        self.store.conn.execute("UPDATE memory SET expires_at=? WHERE id=?", (time.time() - 1, mid))
        self.store.conn.commit()
        self.assertEqual(self.store.l2_expire(), 1)
        row = self.store.conn.execute(
            "SELECT l2_status FROM memory WHERE id=?", (mid,)
        ).fetchone()
        self.assertEqual(row["l2_status"], "expired")


if __name__ == "__main__":
    unittest.main()
