import json
import os
import unittest
from tempfile import TemporaryDirectory

from constants import STATUS_FAILED, STATUS_PUBLISHED
from history import count_today_published
from time_utils import now_kst


class HistoryTest(unittest.TestCase):
    def write_history_record(self, record: dict) -> None:
        with open("history.jsonl", "a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def test_count_today_published_includes_partial_publish_with_post_id(self):
        original_cwd = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            try:
                self.write_history_record(
                    {
                        "published_at": now_kst().isoformat(timespec="seconds"),
                        "status": STATUS_FAILED,
                        "instagram_post_id": "instagram-1",
                        "facebook_post_id": "",
                        "threads_post_id": "",
                    }
                )

                self.assertEqual(count_today_published(), 1)
            finally:
                os.chdir(original_cwd)

    def test_count_today_published_ignores_failed_record_without_post_id(self):
        original_cwd = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            try:
                self.write_history_record(
                    {
                        "published_at": now_kst().isoformat(timespec="seconds"),
                        "status": STATUS_FAILED,
                        "instagram_post_id": "",
                        "facebook_post_id": "",
                        "threads_post_id": "",
                    }
                )

                self.assertEqual(count_today_published(), 0)
            finally:
                os.chdir(original_cwd)

    def test_count_today_published_keeps_published_status_compatible(self):
        original_cwd = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            try:
                self.write_history_record(
                    {
                        "published_at": now_kst().isoformat(timespec="seconds"),
                        "status": STATUS_PUBLISHED,
                        "instagram_post_id": "",
                        "facebook_post_id": "",
                        "threads_post_id": "",
                    }
                )

                self.assertEqual(count_today_published(), 1)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
