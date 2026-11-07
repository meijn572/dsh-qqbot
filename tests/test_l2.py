"""L1 只收确定事实；L2 只召回 hypothesis 且未过期。"""
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

    def test_active_and_expired(self):
        mid = self._add("他可能最近不想吃辣")
        self.assertEqual([x["id"] for x in self.store.l2_active()], [mid])
        self.store.conn.execute("UPDATE memory SET expires_at=? WHERE id=?", (time.time() - 1, mid))
        self.store.conn.commit()
        self.assertEqual(self.store.l2_active(), [])
        self.assertEqual(self.store.l2_expire(), 1)

    def test_set_status(self):
        mid = self._add("他可能最近很忙")
        self.assertTrue(self.store.l2_set_status(mid, "rejected"))
        self.assertEqual(self.store.l2_active(), [])

    def test_promote_to_l1(self):
        mid = self._add("他可能最近不想吃辣", source_ids=[1])
        l1 = self.store.add(mc.MemoryInput(text="主人最近不想吃辣", tier="L1", source_ids=[1]))
        self.store.link(l1, mid, "derived_from", "judgment")
        self.assertTrue(self.store.l2_set_status(mid, "promoted", l1))
        self.assertEqual(self.store.l2_active(), [])
        row = self.store.conn.execute(
            "SELECT l2_status,promoted_to FROM memory WHERE id=?", (mid,)
        ).fetchone()
        self.assertEqual(row["l2_status"], "promoted")
        self.assertEqual(row["promoted_to"], l1)


if __name__ == "__main__":
    unittest.main()
