"""关系三维聚合：L3 delta 直接求和，更新/删除后重算。"""
from __future__ import annotations

import os
import sys
import time
import unittest

from service import memory_core as mc  # noqa: E402


class RelationshipTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mc.MemoryStore(os.path.join(self.tmp.name, "m.db"))
        self.store.set_state(intimacy=0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _add(self, title, **kw):
        return self.store.add(mc.MemoryInput(
            text=title, tier="L3", summary=title, thread_status=kw.pop("status", "standalone"),
            thread_title=title, thread_last_seen_at=time.time(), **kw,
        ))

    def test_sum_and_stage(self):
        self._add("第一次被接住", closeness_delta=5, trust_delta=3)
        rel = self.store.relationship_snapshot()
        self.assertAlmostEqual(rel["closeness"], 5.0)
        self.assertAlmostEqual(rel["trust"], 3.0)
        self.assertAlmostEqual(rel["tension"], 0.0)
        self.assertEqual(self.store.current_stage()["name"], "陌生")

    def test_update_replaces_not_adds(self):
        mid = self._add("那次没回消息", status="open", tension_delta=4, trust_delta=-1)
        self.assertAlmostEqual(self.store.relationship_snapshot()["tension"], 4.0)
        self.store.update_thread(mid, "后来解释了", "closed", tension_delta=0, trust_delta=1)
        rel = self.store.relationship_snapshot()
        self.assertAlmostEqual(rel["tension"], 0.0)
        self.assertAlmostEqual(rel["trust"], 1.0)

    def test_delete_removes_delta(self):
        mid = self._add("临时事件", closeness_delta=7)
        self.assertAlmostEqual(self.store.relationship_snapshot()["closeness"], 7.0)
        self.store.forget(mid)
        self.assertAlmostEqual(self.store.relationship_snapshot()["closeness"], 0.0)

    def test_interaction_count_separate(self):
        self.store.bump_interaction(3)
        state = self.store.get_state()
        self.assertEqual(state["interaction_count"], 3.0)
        self.assertEqual(state["relationship"]["closeness"], 0.0)


if __name__ == "__main__":
    unittest.main()
