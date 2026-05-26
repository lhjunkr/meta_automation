import unittest
from unittest.mock import Mock, patch

from constants import STATUS_FAILED, STATUS_SUCCESS
from facebook_publishing import publish_article_to_facebook_page
from instagram_publishing import publish_article_to_instagram
from models import Article
from threads_publishing import publish_article_to_threads


def build_publishable_article() -> Article:
    article = Article(
        id=1,
        category="경제(KR)",
        title="Test title",
        source="Test source",
        google_link="https://example.com/news",
    )
    article.instagram_caption = "테스트 캡션입니다."
    article.public_image_url = "https://example.com/final.png"
    return article


class PublishingModulesTest(unittest.TestCase):
    @patch("facebook_publishing.requests.post")
    def test_facebook_publish_success_updates_article(self, mock_post):
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {"id": "facebook-post-1"}
        mock_post.return_value = mock_response

        article = build_publishable_article()
        publish_article_to_facebook_page(article)

        self.assertEqual(article.facebook_publish_status, STATUS_SUCCESS)
        self.assertEqual(article.facebook_post_id, "facebook-post-1")
        self.assertEqual(article.facebook_publish_error, "")

    @patch("facebook_publishing.requests.post")
    def test_facebook_publish_failure_updates_article(self, mock_post):
        mock_response = Mock(status_code=400)
        mock_response.json.return_value = {"error": {"message": "bad request"}}
        mock_post.return_value = mock_response

        article = build_publishable_article()
        publish_article_to_facebook_page(article)

        self.assertEqual(article.facebook_publish_status, STATUS_FAILED)
        self.assertEqual(article.facebook_post_id, "")
        self.assertIn("Facebook 게시 실패", article.facebook_publish_error)

    @patch("instagram_publishing.publish_instagram_media")
    @patch("instagram_publishing.wait_for_instagram_media_container")
    @patch("instagram_publishing.create_instagram_media_container")
    def test_instagram_publish_success_updates_article(
        self,
        mock_create_container,
        mock_wait_for_container,
        mock_publish_media,
    ):
        mock_create_container.return_value = "instagram-container-1"
        mock_publish_media.return_value = "instagram-post-1"

        article = build_publishable_article()
        publish_article_to_instagram(article)

        mock_wait_for_container.assert_called_once_with("instagram-container-1")
        self.assertEqual(article.instagram_publish_status, STATUS_SUCCESS)
        self.assertEqual(article.instagram_post_id, "instagram-post-1")
        self.assertEqual(article.instagram_publish_error, "")

    @patch("instagram_publishing.create_instagram_media_container")
    def test_instagram_publish_failure_updates_article(self, mock_create_container):
        mock_create_container.side_effect = RuntimeError("container failed")

        article = build_publishable_article()
        publish_article_to_instagram(article)

        self.assertEqual(article.instagram_publish_status, STATUS_FAILED)
        self.assertEqual(article.instagram_post_id, "")
        self.assertIn("container failed", article.instagram_publish_error)

    @patch("threads_publishing.publish_threads_media")
    @patch("threads_publishing.wait_for_threads_media_container")
    @patch("threads_publishing.create_threads_media_container")
    def test_threads_publish_success_updates_article(
        self,
        mock_create_container,
        mock_wait_for_container,
        mock_publish_media,
    ):
        mock_create_container.return_value = "threads-container-1"
        mock_publish_media.return_value = "threads-post-1"

        article = build_publishable_article()
        publish_article_to_threads(article)

        mock_wait_for_container.assert_called_once_with("threads-container-1")
        self.assertEqual(article.threads_publish_status, STATUS_SUCCESS)
        self.assertEqual(article.threads_post_id, "threads-post-1")
        self.assertEqual(article.threads_publish_error, "")

    @patch("threads_publishing.create_threads_media_container")
    def test_threads_publish_failure_updates_article(self, mock_create_container):
        mock_create_container.side_effect = RuntimeError("threads container failed")

        article = build_publishable_article()
        publish_article_to_threads(article)

        self.assertEqual(article.threads_publish_status, STATUS_FAILED)
        self.assertEqual(article.threads_post_id, "")
        self.assertIn("threads container failed", article.threads_publish_error)


if __name__ == "__main__":
    unittest.main()
