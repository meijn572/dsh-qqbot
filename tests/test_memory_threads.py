import os
import tempfile
import time
import unittest

from service import memory_core as mc


class ThreadStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mc.MemoryStore(
            os.path.join(self.tmp.name, "m.db"),
            schema_path=os.path.join(os.path.dirname(mc.__file__), "schema.sql"),
        )

    def tearDown(self):
        self.store.conn.close()
        self.tmp.cleanup()

    def test_open_and_close_thread(self):
        mid = self.store.add(mc.MemoryInput(
            text="牙疼，准备去看牙",
            tier="L3",
            thread_status="open",
            thread_title="牙疼看牙",
            thread_opened_at=100.0,
            thread_last_seen_at=100.0,
        ))
        self.assertEqual(self.store.open_threads()[0]["title"], "牙疼看牙")
        self.assertTrue(self.store.update_thread(mid, "看完了，只是牙龈发炎", "closed"))
        self.assertEqual(self.store.open_threads(), [])
        self.assertEqual(self.store.find_threads("牙疼")[0]["status"], "closed")

    def test_find_by_alias(self):
        self.store.add(mc.MemoryInput(
            text="牙疼",
            tier="L3",
            thread_status="open",
            thread_title="牙疼看牙",
            thread_aliases=["看牙"],
            thread_last_seen_at=100.0,
        ))
        self.assertEqual(self.store.find_threads("看牙")[0]["title"], "牙疼看牙")

    def test_memory_links(self):
        parent = self.store.add(mc.MemoryInput(text="主人牙疼", tier="L0"))
        child = self.store.add(mc.MemoryInput(text="牙疼事件", tier="L3"))
        self.store.link(child, parent, "derived_from", "evidence")
        self.assertEqual(self.store.links_from(child)[0]["parent_id"], parent)
        self.assertEqual(self.store.links_to(parent)[0]["child_id"], child)

    def test_stale_l1_is_marked_not_deleted(self):
        old = time.time() - 40 * 86400
        mid = self.store.add(mc.MemoryInput(text="很久以前的事", tier="L1", ts=old))
        stats = self.store.mark_lifecycle(l1_days=30, thread_days=14)
        self.assertEqual(stats["stale"], 1)
        row = self.store.conn.execute("SELECT stale_at FROM memory WHERE id=?", (mid,)).fetchone()
        self.assertIsNotNone(row["stale_at"])
        self.assertEqual(self.store.search("很久以前", tiers=None), [])
        self.assertEqual(len(self.store.list_memories(tier="L1", limit=10)["items"]), 1)

    def test_open_thread_becomes_dormant(self):
        old = time.time() - 20 * 86400
        self.store.add(mc.MemoryInput(
            text="很久没提的事", tier="L3", thread_status="open",
            thread_title="很久没提的事", thread_last_seen_at=old,
        ))
        stats = self.store.mark_lifecycle(l1_days=30, thread_days=14)
        self.assertEqual(stats["dormant"], 1)
        self.assertEqual(self.store.open_threads(), [])
        self.assertEqual(self.store.find_threads("很久没提")[0]["status"], "dormant")

    def test_fuzzy_title(self):
        self.store.add(mc.MemoryInput(
            text="万机之神设定讨论", tier="L3", thread_status="open",
            thread_title="万机之神设定讨论", thread_last_seen_at=time.time(),
        ))
        self.assertEqual(self.store.resolve_thread("万机之神")["title"], "万机之神设定讨论")
        self.assertEqual(self.store.find_threads("万机之神")[0]["title"], "万机之神设定讨论")


if __name__ == "__main__":
    unittest.main()
