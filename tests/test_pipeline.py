import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from constants import STATUS_FAILED, STATUS_PUBLISHED, STATUS_SUCCESS
from models import Article
from pipeline import (
    handle_publish_results,
    is_article_complete,
    retry_failed_categories_with_backup,
)


class PipelineTest(unittest.TestCase):
    def build_complete_article(self):
        article = Article(
            id=1,
            category="경제(US)",
            title="Test title",
            source="Test source",
            google_link="https://example.com/news",
        )

        article.status = STATUS_SUCCESS
        article.instagram_caption_status = STATUS_SUCCESS
        article.sdxl_image_prompt_status = STATUS_SUCCESS
        article.image_generation_status = STATUS_SUCCESS
        article.image_overlay_status = STATUS_SUCCESS
        article.r2_upload_status = STATUS_SUCCESS
        article.final_image_path = "/tmp/final.png"
        article.public_image_url = "https://example.com/final.png"

        return article

    def test_is_article_complete_returns_true_for_complete_article(self):
        article = self.build_complete_article()

        self.assertTrue(is_article_complete(article))

    def test_is_article_complete_returns_false_without_public_image_url(self):
        article = self.build_complete_article()
        article.public_image_url = ""

        self.assertFalse(is_article_complete(article))

    def test_is_article_complete_returns_false_for_failed_image_prompt(self):
        article = self.build_complete_article()
        article.sdxl_image_prompt_status = STATUS_FAILED

        self.assertFalse(is_article_complete(article))

    @patch("pipeline.save_failure_report")
    @patch("pipeline.save_failed_categories")
    @patch("pipeline.process_content_pipeline")
    def test_failed_image_prompt_uses_existing_backup_pipeline(
        self,
        mock_process_content_pipeline,
        mock_save_failed_categories,
        mock_save_failure_report,
    ):
        primary_article = self.build_complete_article()
        primary_article.sdxl_image_prompt_status = STATUS_FAILED

        backup_article = self.build_complete_article()
        backup_article.id = 2
        backup_article.selection_rank = "backup"
        primary_article.backup_article = backup_article
        mock_process_content_pipeline.return_value = [backup_article]

        final_articles = retry_failed_categories_with_backup(
            [primary_article],
            Path("/tmp/test-run"),
        )

        mock_process_content_pipeline.assert_called_once_with(
            [backup_article],
            Path("/tmp/test-run"),
        )
        mock_save_failed_categories.assert_called_once_with([], Path("/tmp/test-run"))
        mock_save_failure_report.assert_called_once_with(
            [backup_article],
            Path("/tmp/test-run"),
            [],
        )
        self.assertEqual(final_articles, [backup_article])

    def test_handle_publish_results_records_partial_channel_success_as_failed(self):
        article = self.build_complete_article()
        article.instagram_publish_status = STATUS_SUCCESS
        article.facebook_publish_status = ""
        article.threads_publish_status = ""

        original_cwd = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            try:
                handle_publish_results([article])

                with open("history.jsonl", encoding="utf-8") as history_file:
                    history_record = json.loads(history_file.readline())
            finally:
                os.chdir(original_cwd)

        self.assertEqual(history_record["status"], STATUS_FAILED)
        self.assertEqual(history_record["instagram_post_id"], article.instagram_post_id)

    def test_handle_publish_results_records_meta_success_even_if_threads_failed(self):
        article = self.build_complete_article()
        article.instagram_publish_status = STATUS_SUCCESS
        article.facebook_publish_status = STATUS_SUCCESS
        article.threads_publish_status = STATUS_FAILED

        original_cwd = os.getcwd()

        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            try:
                handle_publish_results([article])

                with open("history.jsonl", encoding="utf-8") as history_file:
                    history_record = json.loads(history_file.readline())
            finally:
                os.chdir(original_cwd)

        self.assertEqual(history_record["status"], STATUS_PUBLISHED)


if __name__ == "__main__":
    unittest.main()
