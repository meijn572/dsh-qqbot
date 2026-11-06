import json
import tempfile
import time
import unittest
from pathlib import Path

import bridge
from qqbot.domains.media import library


class StickerOccurrenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = (library.MEME_DIR, library.INDEX_FILE, library.OCCURRENCE_FILE)
        library.MEME_DIR = root
        library.INDEX_FILE = root / "index.json"
        library.OCCURRENCE_FILE = root / "occurrences.json"

    def tearDown(self):
        library.MEME_DIR, library.INDEX_FILE, library.OCCURRENCE_FILE = self.old
        self.tmp.cleanup()

    def test_occurrence_dedupes_messages(self):
        now = time.time()
        occ_id = library.append_occurrence(
            "happy/a.jpg",
            "private:1",
            {"message_id": "m2", "ts": now, "image_index": 0},
            [
                {"message_id": "m1", "ts": now - 1, "role": "user", "text": "这是奶龙"},
                {"message_id": "m2", "ts": now, "role": "user", "text": "[表情包]", "relation": "anchor"},
                {"message_id": "m1", "ts": now - 1, "role": "user", "text": "这是奶龙"},
            ],
        )
        self.assertTrue(occ_id)
        items = library.pending_occurrences()
        self.assertEqual(len(items), 1)
        self.assertEqual([m["message_id"] for m in items[0]["messages"]], ["m1", "m2"])
        library.mark_occurrences_reviewed([occ_id])
        self.assertEqual(library.pending_occurrences(), [])

    def test_review_status_and_changed_false(self):
        library.index_add("happy/a.jpg", "happy", "旧描述")
        library.review_entry("happy/a.jpg", {"changed": False}, source="model")
        entry = library.load_index()[0]
        self.assertEqual(entry["meta_status"], "reviewed")
        self.assertEqual(entry["meta_source"], "model")
        self.assertEqual(entry["caption"], "旧描述")

    def test_new_entry_starts_pending(self):
        library.index_add("happy/b.jpg", "happy", "新描述")
        entry = library.load_index()[0]
        self.assertEqual(entry["meta_status"], "pending_review")
        self.assertEqual(entry["meta_source"], "vision")

    def test_chat_memory_slice_uses_time_window(self):
        now = time.time()
        bridge.CHAT_MEMORY["private:test"] = [
            {"message_id": "old", "ts": now - 500, "role": "user", "text": "太旧"},
            {"message_id": "before", "ts": now - 10, "role": "user", "text": "之前"},
            {"message_id": "anchor", "ts": now, "role": "user", "text": "[表情包]"},
            {"message_id": "after", "ts": now + 10, "role": "assistant", "text": "之后"},
        ]
        rows = bridge.chat_memory_slice("private:test", now, 180, 120)
        self.assertEqual([r["message_id"] for r in rows], ["before", "anchor", "after"])

    def test_occurrence_merge_dedupes_by_message_id(self):
        merged = bridge._occurrence_messages([
            {"anchor": {"message_id": "a"}, "messages": [
                {"message_id": "m1", "ts": 1, "text": "一"},
                {"message_id": "a", "ts": 2, "text": "[表情包]"},
            ]},
            {"anchor": {"message_id": "b"}, "messages": [
                {"message_id": "m1", "ts": 1, "text": "一"},
                {"message_id": "m2", "ts": 3, "text": "二"},
            ]},
        ])
        self.assertEqual([m["message_id"] for m in merged], ["m1", "a", "m2"])


if __name__ == "__main__":
    unittest.main()
