"""关系状态：模型写 stage/summary，L3 只存一句关系影响。"""
import os
import tempfile
import time
import unittest

from service import memory_core as mc


class RelationshipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mc.MemoryStore(os.path.join(self.tmp.name, "m.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_stage_and_summary(self):
        self.store.set_relationship("亲近", "最近更放松了。", [1, 2])
        rel = self.store.get_relationship()
        self.assertEqual(rel["stage"], "亲近")
        self.assertEqual(rel["summary"], "最近更放松了。")
        self.assertEqual(rel["stage_info"]["index"], 3)

    def test_invalid_stage(self):
        with self.assertRaises(ValueError):
            self.store.set_relationship("很熟", "x")

    def test_impact_roundtrip(self):
        mid = self.store.add(mc.MemoryInput(
            text="那次没回消息",
            tier="L3",
            summary="那次没回消息",
            thread_status="open",
            thread_title="那次没回消息",
            thread_last_seen_at=time.time(),
            relationship_impact="等很久没回，我有点往下掉。",
        ))
        row = self.store.conn.execute(
            "SELECT relationship_impact FROM memory WHERE id=?", (mid,)
        ).fetchone()
        self.assertIn("往下掉", row["relationship_impact"])

    def test_update_impact(self):
        mid = self.store.add(mc.MemoryInput(
            text="那次没回消息", tier="L3", summary="那次没回消息",
            thread_status="open", thread_title="那次没回消息",
            relationship_impact="有点往下掉。",
        ))
        self.store.update_thread(
            mid, "后来解释了", "closed",
            relationship_impact="后来他解释了，心里稳一点。",
        )
        row = self.store.conn.execute(
            "SELECT relationship_impact,thread_status FROM memory WHERE id=?", (mid,)
        ).fetchone()
        self.assertIn("稳一点", row["relationship_impact"])
        self.assertEqual(row["thread_status"], "closed")


if __name__ == "__main__":
    unittest.main()
