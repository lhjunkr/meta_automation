import unittest

from constants import STATUS_SUCCESS
from models import Article
from pipeline import is_article_complete


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


if __name__ == "__main__":
    unittest.main()