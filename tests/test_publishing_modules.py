import unittest
from unittest.mock import Mock, patch

from constants import STATUS_FAILED, STATUS_PUBLISHED, STATUS_SUCCESS
from facebook_publishing import publish_article_to_facebook_page
from instagram_publishing import (
    is_retryable_instagram_publish_error,
    publish_article_to_instagram,
    publish_instagram_media_with_retry,
)
from models import Article
from publishing import publish_to_social_channels
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

    def test_instagram_publish_retryable_error_detection(self):
        self.assertTrue(
            is_retryable_instagram_publish_error(
                RuntimeError("Instagram 게시 실패: Media ID is not available")
            )
        )
        self.assertFalse(
            is_retryable_instagram_publish_error(
                RuntimeError("Instagram 게시 실패: invalid token")
            )
        )

    @patch("instagram_publishing.time.sleep")
    @patch("instagram_publishing.publish_instagram_media")
    def test_instagram_publish_media_retries_temporary_media_error(
        self,
        mock_publish_media,
        mock_sleep,
    ):
        mock_publish_media.side_effect = [
            RuntimeError("Instagram 게시 실패: Media ID is not available"),
            "instagram-post-1",
        ]

        instagram_post_id = publish_instagram_media_with_retry("instagram-container-1")

        self.assertEqual(instagram_post_id, "instagram-post-1")
        self.assertEqual(mock_publish_media.call_count, 2)
        mock_sleep.assert_called_once()

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

    @patch("publishing.publish_article_to_threads")
    @patch("publishing.publish_article_to_facebook_page")
    @patch("publishing.publish_article_to_instagram")
    @patch("publishing.get_publish_delay_seconds", return_value=0)
    @patch("publishing.is_already_published", return_value=False)
    @patch("publishing.count_today_published", return_value=0)
    @patch("publishing.preflight_threads_publishing")
    @patch("publishing.preflight_meta_publishing")
    def test_threads_preflight_failure_does_not_block_meta_channels(
        self,
        mock_meta_preflight,
        mock_threads_preflight,
        mock_count_today_published,
        mock_is_already_published,
        mock_get_delay,
        mock_publish_instagram,
        mock_publish_facebook,
        mock_publish_threads,
    ):
        def mark_instagram_success(article: Article) -> Article:
            article.instagram_publish_status = STATUS_SUCCESS
            return article

        def mark_facebook_success(article: Article) -> Article:
            article.facebook_publish_status = STATUS_SUCCESS
            return article

        mock_threads_preflight.side_effect = RuntimeError("threads token expired")
        mock_publish_instagram.side_effect = mark_instagram_success
        mock_publish_facebook.side_effect = mark_facebook_success

        article = build_publishable_article()
        published_articles = publish_to_social_channels([article])

        mock_meta_preflight.assert_called_once()
        mock_threads_preflight.assert_called_once()
        mock_publish_instagram.assert_called_once_with(article)
        mock_publish_facebook.assert_called_once_with(article)
        mock_publish_threads.assert_not_called()
        self.assertEqual(published_articles, [article])
        self.assertEqual(article.publish_status, STATUS_PUBLISHED)
        self.assertEqual(article.threads_publish_status, STATUS_FAILED)
        self.assertIn("threads token expired", article.threads_publish_error)


if __name__ == "__main__":
    unittest.main()
