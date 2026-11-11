import asyncio
import unittest

from qqbot.domains.growth import emotion


class ParseEmotionTests(unittest.TestCase):
    def test_valid(self):
        got = emotion.parse_emotion('{"label":"心动又警惕","valence":0.5,"arousal":0.4,"reason":"接不住"}')
        self.assertEqual(got["label"], "心动又警惕")
        self.assertEqual(got["valence"], 0.5)
        self.assertEqual(got["arousal"], 0.4)

    def test_skip(self):
        self.assertIsNone(emotion.parse_emotion('{"skip":true}'))

    def test_clamp(self):
        got = emotion.parse_emotion('{"label":"复杂","valence":9,"arousal":-2}')
        self.assertEqual(got["valence"], 1.0)
        self.assertEqual(got["arousal"], 0.0)

    def test_missing_valence_defaults_neutral(self):
        got = emotion.parse_emotion('{"label":"讪讪"}')
        self.assertEqual(got["valence"], 0.0)
        self.assertEqual(got["arousal"], 0.5)


class ReviewTurnTests(unittest.TestCase):
    def test_writes_idle_review_source(self):
        calls = []
        original = emotion.set_emotion

        async def fake_set(*args, **kwargs):
            calls.append((args, kwargs))

        async def fake_turn(prompt):
            self.assertIn("主人：在吗", prompt)
            return '{"label":"暖","valence":0.6,"arousal":0.2,"reason":"被接住"}'

        emotion.set_emotion = fake_set
        try:
            got = asyncio.run(emotion.review_turn(fake_turn, "主人：在吗\n洄：在", ts_start=100.0, ts_end=200.0))
        finally:
            emotion.set_emotion = original
        self.assertEqual(got["label"], "暖")
        self.assertEqual(calls[0][1]["source"], "idle-review")
        self.assertEqual(calls[0][1]["ts_start"], 100.0)
        self.assertEqual(calls[0][1]["ts_end"], 200.0)

    def test_skip_writes_nothing(self):
        calls = []
        original = emotion.set_emotion

        async def fake_set(*args, **kwargs):
            calls.append((args, kwargs))

        async def fake_turn(prompt):
            return '{"skip":true}'

        emotion.set_emotion = fake_set
        try:
            got = asyncio.run(emotion.review_turn(fake_turn, "主人：在吗\n洄：在"))
        finally:
            emotion.set_emotion = original
        self.assertIsNone(got)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
