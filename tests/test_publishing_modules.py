import unittest
from unittest.mock import Mock, patch

from constants import (
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_SUCCESS,
    STORY_STATUS_SKIPPED_FEED_NOT_PUBLISHED,
    STORY_STATUS_SKIPPED_NO_STORY_IMAGE,
)
from facebook_publishing import (
    publish_article_story_to_facebook_page,
    publish_article_to_facebook_page,
)
from instagram_publishing import (
    create_instagram_story_container,
    is_retryable_instagram_publish_error,
    publish_article_story_to_instagram,
    publish_article_to_instagram,
    publish_instagram_media_with_retry,
)
from models import Article
from publishing import (
    get_first_publish_delay_seconds,
    get_publish_delay_seconds,
    publish_article_stories,
    publish_to_social_channels,
)
from threads_publishing import (
    THREADS_TEXT_MAX_LENGTH,
    build_threads_post_text,
    create_threads_media_container,
    publish_article_to_threads,
)


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
    article.public_story_image_url = "https://example.com/story.jpg"
    return article


def build_json_response(status_code: int, data: dict) -> Mock:
    response = Mock(status_code=status_code)
    response.json.return_value = data
    return response


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

    @patch("facebook_publishing.requests.post")
    def test_facebook_story_uploads_unpublished_photo_then_publishes_story(self, mock_post):
        mock_post.side_effect = [
            build_json_response(200, {"id": "facebook-photo-1"}),
            build_json_response(200, {"success": True, "post_id": "facebook-story-1"}),
        ]

        article = build_publishable_article()
        publish_article_story_to_facebook_page(article)

        photo_call, story_call = mock_post.call_args_list
        self.assertTrue(photo_call.args[0].endswith("/photos"))
        self.assertEqual(photo_call.kwargs["data"]["published"], "false")
        self.assertEqual(photo_call.kwargs["data"]["url"], "https://example.com/story.jpg")
        self.assertTrue(story_call.args[0].endswith("/photo_stories"))
        self.assertEqual(story_call.kwargs["data"]["photo_id"], "facebook-photo-1")
        self.assertEqual(article.facebook_story_status, STATUS_SUCCESS)
        self.assertEqual(article.facebook_story_id, "facebook-story-1")
        self.assertEqual(article.facebook_story_error, "")

    @patch("facebook_publishing.requests.post")
    def test_facebook_story_failure_updates_article(self, mock_post):
        mock_post.side_effect = [
            build_json_response(200, {"id": "facebook-photo-1"}),
            build_json_response(400, {"error": {"message": "permission denied"}}),
        ]

        article = build_publishable_article()
        publish_article_story_to_facebook_page(article)

        self.assertEqual(article.facebook_story_status, STATUS_FAILED)
        self.assertEqual(article.facebook_story_id, "")
        self.assertIn("Facebook 스토리 게시 실패", article.facebook_story_error)

    @patch("instagram_publishing.requests.post")
    def test_instagram_story_container_uses_stories_media_type(self, mock_post):
        mock_post.return_value = build_json_response(200, {"id": "instagram-story-container-1"})

        article = build_publishable_article()
        creation_id = create_instagram_story_container(article)

        payload = mock_post.call_args.kwargs["data"]
        self.assertEqual(creation_id, "instagram-story-container-1")
        self.assertEqual(payload["media_type"], "STORIES")
        self.assertEqual(payload["image_url"], "https://example.com/story.jpg")
        self.assertNotIn("caption", payload)

    @patch("instagram_publishing.publish_instagram_media")
    @patch("instagram_publishing.wait_for_instagram_media_container")
    @patch("instagram_publishing.create_instagram_story_container")
    def test_instagram_story_publish_success_updates_article(
        self,
        mock_create_container,
        mock_wait_for_container,
        mock_publish_media,
    ):
        mock_create_container.return_value = "instagram-story-container-1"
        mock_publish_media.return_value = "instagram-story-1"

        article = build_publishable_article()
        publish_article_story_to_instagram(article)

        mock_wait_for_container.assert_called_once_with("instagram-story-container-1")
        self.assertEqual(article.instagram_story_status, STATUS_SUCCESS)
        self.assertEqual(article.instagram_story_id, "instagram-story-1")
        self.assertEqual(article.instagram_story_error, "")

    @patch("instagram_publishing.create_instagram_story_container")
    def test_instagram_story_publish_failure_updates_article(self, mock_create_container):
        mock_create_container.side_effect = RuntimeError("story container failed")

        article = build_publishable_article()
        publish_article_story_to_instagram(article)

        self.assertEqual(article.instagram_story_status, STATUS_FAILED)
        self.assertEqual(article.instagram_story_id, "")
        self.assertIn("story container failed", article.instagram_story_error)

    @patch("publishing.publish_article_story_to_facebook_page")
    @patch("publishing.publish_article_story_to_instagram")
    def test_stories_are_published_only_for_successful_feed_channels(
        self,
        mock_publish_instagram_story,
        mock_publish_facebook_story,
    ):
        article = build_publishable_article()
        article.instagram_publish_status = STATUS_SUCCESS
        article.facebook_publish_status = STATUS_FAILED

        publish_article_stories(article)

        mock_publish_instagram_story.assert_called_once_with(article)
        mock_publish_facebook_story.assert_not_called()
        self.assertEqual(article.facebook_story_status, STORY_STATUS_SKIPPED_FEED_NOT_PUBLISHED)

    @patch("publishing.publish_article_story_to_facebook_page")
    @patch("publishing.publish_article_story_to_instagram")
    def test_stories_are_skipped_without_story_image(
        self,
        mock_publish_instagram_story,
        mock_publish_facebook_story,
    ):
        article = build_publishable_article()
        article.public_story_image_url = ""
        article.instagram_publish_status = STATUS_SUCCESS
        article.facebook_publish_status = STATUS_SUCCESS

        publish_article_stories(article)

        mock_publish_instagram_story.assert_not_called()
        mock_publish_facebook_story.assert_not_called()
        self.assertEqual(article.instagram_story_status, STORY_STATUS_SKIPPED_NO_STORY_IMAGE)
        self.assertEqual(article.facebook_story_status, STORY_STATUS_SKIPPED_NO_STORY_IMAGE)

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

    def test_threads_post_text_is_truncated_to_api_limit(self):
        caption = "가" * (THREADS_TEXT_MAX_LENGTH + 20)

        threads_text = build_threads_post_text(caption)

        self.assertLessEqual(len(threads_text), THREADS_TEXT_MAX_LENGTH)
        self.assertTrue(threads_text.endswith("..."))

    @patch("threads_publishing.requests.post")
    @patch("threads_publishing.validate_threads_config")
    def test_threads_media_container_uses_limited_text(
        self,
        mock_validate_threads_config,
        mock_post,
    ):
        mock_validate_threads_config.return_value = ("threads-token", "threads-user")
        mock_response = Mock(status_code=200)
        mock_response.json.return_value = {"id": "threads-container-1"}
        mock_post.return_value = mock_response

        article = build_publishable_article()
        article.instagram_caption = "가" * (THREADS_TEXT_MAX_LENGTH + 20)

        create_threads_media_container(article)

        payload = mock_post.call_args.kwargs["data"]
        self.assertLessEqual(len(payload["text"]), THREADS_TEXT_MAX_LENGTH)

    @patch("publishing.random.randint", return_value=120)
    @patch.dict(
        "os.environ",
        {
            "UPLOAD_WINDOW_MINUTES": "15",
            "POST_SPACING_MINUTES": "5",
        },
    )
    def test_publish_delays_stay_inside_upload_window(self, mock_randint):
        first_delay_seconds = get_first_publish_delay_seconds(publish_count=3)
        delay_seconds = [
            get_publish_delay_seconds(0, first_delay_seconds),
            get_publish_delay_seconds(1, first_delay_seconds),
            get_publish_delay_seconds(2, first_delay_seconds),
        ]

        self.assertEqual(delay_seconds, [120, 300, 300])
        self.assertLessEqual(sum(delay_seconds), 15 * 60)
        mock_randint.assert_called_once_with(0, 5 * 60)

    @patch("publishing.publish_article_stories")
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
        mock_publish_stories,
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
        mock_publish_stories.assert_called_once_with(article)
        self.assertEqual(published_articles, [article])
        self.assertEqual(article.publish_status, STATUS_PUBLISHED)
        self.assertEqual(article.threads_publish_status, STATUS_FAILED)
        self.assertIn("threads token expired", article.threads_publish_error)


if __name__ == "__main__":
    unittest.main()
