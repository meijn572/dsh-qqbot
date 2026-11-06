import unittest

from service.evidence_match import match_evidence, normalize


ROWS = [
    {"id": 1, "text": "主人：你给自己取个名字吧\n我：叫洄，洄游的洄"},
    {"id": 2, "text": "主人：今天加班到现在，累死了"},
]


class EvidenceMatchTest(unittest.TestCase):
    def test_exact_substring(self):
        ids, status = match_evidence(["主人：你给自己取个名字吧"], ROWS)
        self.assertEqual(ids, [1])
        self.assertEqual(status, "verified")

    def test_punctuation_tolerant(self):
        ids, status = match_evidence(["主人 你给自己取个名字吧"], ROWS)
        self.assertEqual(ids, [1])
        self.assertEqual(status, "verified")

    def test_fuzzy_minor_copy(self):
        ids, status = match_evidence(["主人：你给自己取个名字"], ROWS)
        self.assertEqual(ids, [1])
        self.assertEqual(status, "verified")

    def test_no_match(self):
        ids, status = match_evidence(["主人：明天去北京"], ROWS)
        self.assertEqual(ids, [])
        self.assertEqual(status, "unverified")

    def test_empty_evidence(self):
        ids, status = match_evidence([], ROWS)
        self.assertEqual(ids, [])
        self.assertEqual(status, "unverified")

    def test_normalize(self):
        self.assertEqual(normalize("主人：你好，呀！"), "主人你好呀")


if __name__ == "__main__":
    unittest.main()
