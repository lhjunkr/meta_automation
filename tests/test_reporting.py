import unittest

from constants import STATUS_FAILED, STATUS_SUCCESS
from models import Article
from reporting import build_run_execution_report, build_run_failure_report


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

    def test_execution_report_includes_channel_counts_and_models(self):
        article = Article(
            id=1,
            category="경제(KR)",
            title="Uploaded article",
            source="Test source",
            google_link="https://example.com/news",
        )
        article.instagram_caption_model = "gemini-2.5-flash-lite"
        article.image_generation_model = "black-forest-labs/FLUX.1-dev"
        article.instagram_publish_status = STATUS_SUCCESS
        article.instagram_post_id = "instagram-1"
        article.facebook_publish_status = STATUS_SUCCESS
        article.facebook_post_id = "facebook-1"
        article.threads_publish_status = STATUS_FAILED

        report = build_run_execution_report([article])

        self.assertIn("Instagram: 1", report)
        self.assertIn("Facebook: 1", report)
        self.assertIn("Threads: 0", report)
        self.assertIn("Title: Uploaded article", report)
        self.assertIn("Caption/Text Model: gemini-2.5-flash-lite", report)
        self.assertIn("Image Model: black-forest-labs/FLUX.1-dev", report)
        self.assertIn("Instagram: success (instagram-1)", report)
        self.assertIn("Facebook: success (facebook-1)", report)
        self.assertIn("Threads: failed", report)


if __name__ == "__main__":
    unittest.main()
