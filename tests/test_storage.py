import unittest
from datetime import timedelta

from storage import (
    build_r2_history_key,
    is_recent_history_key,
    parse_r2_history_date,
)
from time_utils import today_kst


class StorageTest(unittest.TestCase):
    def test_build_r2_history_key_uses_private_date_prefix(self):
        self.assertEqual(
            build_r2_history_key("2026-05-27"),
            "private/history/2026-05-27/history.jsonl",
        )

    def test_parse_r2_history_date_returns_date_for_history_key(self):
        history_date = parse_r2_history_date("private/history/2026-05-27/history.jsonl")

        self.assertIsNotNone(history_date)
        assert history_date is not None
        self.assertEqual(history_date.isoformat(), "2026-05-27")

    def test_parse_r2_history_date_ignores_public_image_key(self):
        self.assertIsNone(parse_r2_history_date("2026-05-27/article_1_final.png"))

    def test_is_recent_history_key_keeps_recent_dates_only(self):
        today_key = build_r2_history_key(today_kst().isoformat())
        old_key = build_r2_history_key((today_kst() - timedelta(days=3)).isoformat())

        self.assertTrue(is_recent_history_key(today_key, keep_days=3))
        self.assertFalse(is_recent_history_key(old_key, keep_days=3))


if __name__ == "__main__":
    unittest.main()
