import os
import tempfile
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


if __name__ == "__main__":
    unittest.main()
