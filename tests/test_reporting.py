import unittest

from constants import STATUS_FAILED
from models import Article
from reporting import build_run_failure_report


class ReportingTest(unittest.TestCase):
    def test_failure_report_includes_category_failures(self):
        report = build_run_failure_report(
            [],
            [
                {
                    "category": "경제(KR)",
                    "primary_id": 10,
                    "backup_id": 11,
                    "reason": "primary_and_backup_failed",
                }
            ],
        )

        self.assertIn("Category Failures", report)
        self.assertIn("category:경제(KR)", report)
        self.assertIn("reason:primary_and_backup_failed", report)

    def test_failure_report_includes_channel_failures(self):
        article = Article(
            id=1,
            category="경제(US)",
            title="Test title",
            source="Test source",
            google_link="https://example.com/news",
        )
        article.threads_publish_status = STATUS_FAILED

        report = build_run_failure_report([article])

        self.assertIn("threads:failed", report)


if __name__ == "__main__":
    unittest.main()
