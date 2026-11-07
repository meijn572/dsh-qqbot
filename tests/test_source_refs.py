import os
import sys
import tempfile
import unittest

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "..", "service")
sys.path.insert(0, SERVICE_DIR)

from service import memory_core as mc
from service.extractor import Extractor, ExtractConfig, _refs_to_ids, _tier_of_refs


class SourceRefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = mc.MemoryStore(
            os.path.join(self.tmp.name, "m.db"),
            schema_path=os.path.join(os.path.dirname(mc.__file__), "schema.sql"),
        )
        self.rows = []
        for text in ("L0 a", "L0 b"):
            mid = self.store.add(mc.MemoryInput(text=text, tier="L0"))
            self.rows.append({"id": mid, "tier": "L0", "text": text})
        self.ex = Extractor(None, self.store, ExtractConfig(enabled=True))

    def tearDown(self):
        self.store.conn.close()
        self.tmp.cleanup()

    def test_ref_mapping(self):
        self.assertEqual(_refs_to_ids([2, 99], self.rows), [self.rows[1]["id"]])
        self.assertEqual(_tier_of_refs([1, 2], self.rows), [("L0", self.rows[0]["id"]), ("L0", self.rows[1]["id"])])

    def test_ref_writes_source_and_link(self):
        self.ex._decide = lambda fact, idx, neighbors: {"op": "ADD", "reason": "test"}
        res = self.ex._apply_facts(
            [{"text": "事实", "source_refs": [2]}],
            allowed_tiers={"L1"},
            source_rows=self.rows,
        )
        mid = res["ids"][0]
        row = self.store.conn.execute(
            "SELECT source_ids, source_status FROM memory WHERE id=?", (mid,)
        ).fetchone()
        self.assertEqual(row["source_ids"], f"[{self.rows[1]['id']}]")
        self.assertEqual(row["source_status"], "verified")
        self.assertEqual(self.store.links_from(mid)[0]["parent_id"], self.rows[1]["id"])

    def test_fallback_to_quote(self):
        self.ex._decide = lambda fact, idx, neighbors: {"op": "ADD", "reason": "test"}
        res = self.ex._apply_facts(
            [{"text": "事实", "evidence": ["L0 a"]}],
            allowed_tiers={"L1"},
            source_rows=self.rows,
        )
        row = self.store.conn.execute(
            "SELECT source_ids, source_status FROM memory WHERE id=?", (res["ids"][0],)
        ).fetchone()
        self.assertEqual(row["source_ids"], f"[{self.rows[0]['id']}]")
        self.assertEqual(row["source_status"], "verified")


if __name__ == "__main__":
    unittest.main()
