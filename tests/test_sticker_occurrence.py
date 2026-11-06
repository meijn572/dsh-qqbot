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
            "run-1",
            now - 180,
            now + 120,
            [
                {"seq": 1, "message_id": "m1", "ts": now - 1, "role": "user", "text": "这是奶龙"},
                {"seq": 2, "message_id": "m2", "ts": now, "role": "user", "text": "", "images": [{"path": "x"}]},
                {"seq": 1, "message_id": "m1", "ts": now - 1, "role": "user", "text": "这是奶龙"},
            ],
        )
        self.assertTrue(occ_id)
        items = library.pending_occurrences()
        self.assertEqual(len(items), 1)
        self.assertEqual([m["seq"] for m in items[0]["messages"]], [1, 2])
        self.assertEqual(items[0]["run_id"], "run-1")
        self.assertTrue(items[0]["messages"][1]["images"])
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

    def test_chat_memory_slice_uses_seq_and_time_window(self):
        now = time.time()
        bridge.CHAT_MEMORY["private:test"] = [
            {"seq": 1, "ts": now - 500, "role": "user", "text": "太旧"},
            {"seq": 2, "ts": now - 10, "role": "user", "text": "之前"},
            {"seq": 3, "ts": now, "role": "user", "text": ""},
            {"seq": 4, "ts": now + 10, "role": "assistant", "text": "之后"},
        ]
        rows = bridge.chat_memory_slice("private:test", now, 180, 120)
        self.assertEqual([r["seq"] for r in rows], [2, 3, 4])

    def test_occurrence_merge_uses_run_and_seq(self):
        merged = bridge._occurrence_messages([
            {"run_id": "run-1", "messages": [
                {"seq": 1, "ts": 1, "text": "一"},
                {"seq": 2, "ts": 2, "text": "", "images": [{"rel": "a.jpg"}]},
            ]},
            {"run_id": "run-1", "messages": [
                {"seq": 1, "ts": 1, "text": "一"},
                {"seq": 3, "ts": 3, "text": "二"},
            ]},
        ])
        self.assertEqual([m["seq"] for m in merged], [1, 2, 3])

    def test_timeline_renders_images_and_gap(self):
        text = bridge._render_timeline([
            {"run_id": "run-1", "rel": "a.jpg", "messages": [
                {"seq": 1, "ts": 1, "role": "user", "speaker": "九歌", "text": "看这个"},
                {"seq": 2, "ts": 2, "role": "user", "speaker": "九歌", "text": "", "images": [{"rel": "a.jpg"}]},
                {"seq": 5, "ts": 5, "role": "assistant", "speaker": "洄", "text": "看到了"},
            ]},
        ])
        self.assertIn("[#1] 九歌：看这个", text)
        self.assertIn("[#2] 九歌：[图片：a.jpg]", text)
        self.assertIn("中间有 2 条消息未纳入", text)


if __name__ == "__main__":
    unittest.main()
