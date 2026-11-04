import tempfile
import unittest
from pathlib import Path

from qqbot.domains.growth import proposals


class ReviewProposalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = proposals.PROPOSALS
        proposals.PROPOSALS = Path(self.tmp.name) / "review-proposals.json"

    def tearDown(self):
        proposals.PROPOSALS = self.old
        self.tmp.cleanup()

    def test_add_and_status(self):
        items = proposals.add_proposals("judgment", [{"op": "add", "text": "先查再答"}], "测试")
        self.assertEqual(len(items), 1)
        self.assertEqual(len(proposals.pending()), 1)
        self.assertTrue(proposals.set_status(items[0]["id"], "applied"))
        self.assertEqual(proposals.pending(), [])

    def test_commitment_dedup(self):
        first = proposals.add_commitment("他难受时先听完")
        second = proposals.add_commitment("他难受时先听完")
        self.assertIsNotNone(first)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
