import unittest
from unittest.mock import patch

from constants import ARTICLE_STATUS_RESOLVE_FAILED, STATUS_SUCCESS
from models import Article
from news import (
    fetch_selected_article_bodies,
    is_decoded_result_successful,
    resolve_article_url,
    resolve_selected_article_links,
)


class ResolveArticleUrlTest(unittest.TestCase):
    def test_accepts_success_key_from_googlenewsdecoder_0_2(self):
        decoded_result = {
            "success": True,
            "decoded_url": "https://example.com/article",
        }

        with patch("news.gnewsdecoder", return_value=decoded_result):
            self.assertEqual(
                resolve_article_url("https://news.google.com/rss/articles/x"),
                "https://example.com/article",
            )

    def test_accepts_status_key_from_googlenewsdecoder_0_1(self):
        decoded_result = {
            "status": True,
            "decoded_url": "https://example.com/article",
        }

        with patch("news.gnewsdecoder", return_value=decoded_result):
            self.assertEqual(
                resolve_article_url("https://news.google.com/rss/articles/x"),
                "https://example.com/article",
            )

    def test_returns_empty_string_when_decoding_fails(self):
        decoded_result = {"success": False, "message": "Invalid Google News URL format."}

        with patch("news.gnewsdecoder", return_value=decoded_result):
            self.assertEqual(
                resolve_article_url("https://news.google.com/rss/articles/x"),
                "",
            )

    def test_returns_empty_string_when_decoded_url_is_missing(self):
        with patch("news.gnewsdecoder", return_value={"success": True}):
            self.assertEqual(
                resolve_article_url("https://news.google.com/rss/articles/x"),
                "",
            )

    def test_returns_empty_string_when_decoder_raises(self):
        with patch("news.gnewsdecoder", side_effect=RuntimeError("boom")):
            self.assertEqual(
                resolve_article_url("https://news.google.com/rss/articles/x"),
                "",
            )

    def test_is_decoded_result_successful_rejects_failure_payloads(self):
        self.assertFalse(is_decoded_result_successful({"success": False, "message": "x"}))
        self.assertFalse(is_decoded_result_successful({"status": False, "message": "x"}))
        self.assertFalse(is_decoded_result_successful({}))


class ResolveSelectedArticleLinksTest(unittest.TestCase):
    def build_article(self, article_id):
        return Article(
            id=article_id,
            category="종합(KR)",
            title=f"Test title {article_id}",
            source="Test source",
            google_link=f"https://news.google.com/rss/articles/{article_id}",
        )

    def test_sets_resolved_link_for_each_article(self):
        articles = [self.build_article(1), self.build_article(2)]

        with patch("news.resolve_article_url", side_effect=["https://a", "https://b"]):
            resolve_selected_article_links(articles)

        self.assertEqual([article.resolved_link for article in articles], ["https://a", "https://b"])

    def test_warns_once_when_every_article_fails_to_resolve(self):
        articles = [self.build_article(1), self.build_article(2)]

        with patch("news.resolve_article_url", return_value=""):
            with patch("builtins.print") as mocked_print:
                resolve_selected_article_links(articles)

        printed = " ".join(str(call.args[0]) for call in mocked_print.call_args_list)
        self.assertIn("URL 정화가 모두 실패했습니다", printed)

    def test_does_not_warn_when_one_article_resolves(self):
        articles = [self.build_article(1), self.build_article(2)]

        with patch("news.resolve_article_url", side_effect=["https://a", ""]):
            with patch("builtins.print") as mocked_print:
                resolve_selected_article_links(articles)

        printed = " ".join(str(call.args[0]) for call in mocked_print.call_args_list)
        self.assertNotIn("URL 정화가 모두 실패했습니다", printed)


class FetchSelectedArticleBodiesTest(unittest.TestCase):
    def build_article(self):
        return Article(
            id=1,
            category="종합(KR)",
            title="Test title",
            source="Test source",
            google_link="https://news.google.com/rss/articles/1",
        )

    def test_marks_resolve_failed_without_resolved_link(self):
        article = self.build_article()
        article.resolved_link = ""

        fetch_selected_article_bodies([article])

        self.assertEqual(article.status, ARTICLE_STATUS_RESOLVE_FAILED)
        self.assertEqual(article.body, "")

    def test_fetches_body_when_resolved_link_exists(self):
        article = self.build_article()
        article.resolved_link = "https://example.com/article"

        with patch("news.fetch_article_body", return_value=("본문", STATUS_SUCCESS)):
            fetch_selected_article_bodies([article])

        self.assertEqual(article.status, STATUS_SUCCESS)
        self.assertEqual(article.body, "본문")


if __name__ == "__main__":
    unittest.main()
