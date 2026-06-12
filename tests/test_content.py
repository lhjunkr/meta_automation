import unittest
from unittest.mock import Mock, patch

from google.genai import errors

from constants import STATUS_FAILED
from content import (
    IMAGE_PROMPT_RESPONSE_MARKER,
    MAX_IMAGE_PROMPT_BODY_CHARS,
    build_sdxl_image_prompt,
    generate_sdxl_image_prompt,
    generate_sdxl_image_prompts,
    validate_sdxl_image_prompt_response,
)
from models import Article


class ContentTest(unittest.TestCase):
    def test_image_prompt_includes_article_context_and_truncates_body(self):
        article = Article(
            id=1,
            category="경제(KR)",
            title="국산 AI 반도체 투자 확대",
            source="테스트 언론사",
            google_link="https://example.com/news",
        )
        article.instagram_caption = "국산 AI 반도체 기업에 대한 투자가 확대됐습니다."
        article.body = ("가" * MAX_IMAGE_PROMPT_BODY_CHARS) + "제외될본문"

        prompt = build_sdxl_image_prompt(article)

        self.assertIn(f"- Article Title: {article.title}", prompt)
        self.assertIn(f"- Category: {article.category}", prompt)
        self.assertIn(f"- Generated Caption: {article.instagram_caption}", prompt)
        self.assertIn("가" * MAX_IMAGE_PROMPT_BODY_CHARS, prompt)
        self.assertNotIn("제외될본문", prompt)

    def test_image_prompt_prioritizes_grounded_subject_action_and_location(self):
        article = Article(
            id=2,
            category="경제(US)",
            title="반도체 공장 투자 발표",
            source="테스트 언론사",
            google_link="https://example.com/semiconductor",
        )
        article.instagram_caption = "반도체 기업이 새 생산시설 투자를 발표했습니다."
        article.body = "기업은 미국 내 반도체 생산시설을 확장할 계획입니다."

        prompt = build_sdxl_image_prompt(article)

        self.assertIn("one primary subject, one visible action or event", prompt)
        self.assertIn("most specific supported location or setting", prompt)
        self.assertIn(
            "primary subject, visible action or event, and location or setting, in that order",
            prompt,
        )
        self.assertIn("Do not combine several unrelated scenes", prompt)
        self.assertIn("Do not substitute a generic office", prompt)

    def test_image_prompt_response_validation_accepts_required_format(self):
        raw_text = (
            f"{IMAGE_PROMPT_RESPONSE_MARKER}\n"
            "semiconductor fabrication facility, engineers inspecting silicon wafers, "
            "United States industrial setting"
        )

        image_prompt = validate_sdxl_image_prompt_response(raw_text)

        self.assertTrue(image_prompt.startswith("semiconductor fabrication facility"))

    def test_image_prompt_response_validation_rejects_empty_response(self):
        with self.assertRaisesRegex(ValueError, "비어 있습니다"):
            validate_sdxl_image_prompt_response("")

    def test_image_prompt_response_validation_rejects_short_response(self):
        raw_text = f"{IMAGE_PROMPT_RESPONSE_MARKER}\nchip, factory"

        with self.assertRaisesRegex(ValueError, "지나치게 짧습니다"):
            validate_sdxl_image_prompt_response(raw_text)

    def test_image_prompt_response_validation_rejects_missing_marker(self):
        raw_text = (
            "semiconductor facility, engineers inspecting wafers, "
            "realistic editorial photography"
        )

        with self.assertRaisesRegex(ValueError, "필수 마커가 없습니다"):
            validate_sdxl_image_prompt_response(raw_text)

    def test_image_prompt_response_validation_rejects_non_comma_format(self):
        raw_text = (
            f"{IMAGE_PROMPT_RESPONSE_MARKER}\n"
            "semiconductor engineers inspecting silicon wafers in a production facility"
        )

        with self.assertRaisesRegex(ValueError, "쉼표 구분 형식이 아닙니다"):
            validate_sdxl_image_prompt_response(raw_text)

    def test_invalid_response_does_not_trigger_additional_gemini_call(self):
        article = Article(
            id=3,
            category="경제(KR)",
            title="반도체 투자",
            source="테스트 언론사",
            google_link="https://example.com/investment",
        )
        article.instagram_caption = "반도체 생산시설 투자가 확대됐습니다."
        article.body = "기업이 국내 생산시설에 투자합니다."

        mock_client = Mock()
        mock_client.models.generate_content.return_value = Mock(text="")

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch("content.genai.Client", return_value=mock_client),
        ):
            generate_sdxl_image_prompt(article)

        mock_client.models.generate_content.assert_called_once()
        self.assertEqual(article.sdxl_image_prompt, "")
        self.assertEqual(article.sdxl_image_prompt_status, STATUS_FAILED)

    def test_rate_limit_error_is_recorded_without_additional_retry(self):
        article = self.build_article(article_id=4)
        mock_client = Mock()
        mock_client.models.generate_content.side_effect = errors.ClientError(
            429,
            {"error": {"code": 429, "message": "rate limited"}},
        )

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch("content.genai.Client", return_value=mock_client),
        ):
            generate_sdxl_image_prompt(article)

        mock_client.models.generate_content.assert_called_once()
        self.assertEqual(article.sdxl_image_prompt, "")
        self.assertEqual(article.sdxl_image_prompt_status, STATUS_FAILED)

    def test_service_unavailable_error_does_not_stop_next_article(self):
        failed_article = self.build_article(article_id=5)
        successful_article = self.build_article(article_id=6)

        failed_client = Mock()
        failed_client.models.generate_content.side_effect = errors.ServerError(
            503,
            {"error": {"code": 503, "message": "high demand"}},
        )
        successful_client = Mock()
        successful_client.models.generate_content.return_value = Mock(
            text=(
                f"{IMAGE_PROMPT_RESPONSE_MARKER}\n"
                "semiconductor production facility, engineers inspecting silicon wafers, "
                "Korean industrial setting"
            )
        )

        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
            patch(
                "content.genai.Client",
                side_effect=[failed_client, successful_client],
            ),
        ):
            generate_sdxl_image_prompts([failed_article, successful_article])

        failed_client.models.generate_content.assert_called_once()
        successful_client.models.generate_content.assert_called_once()
        self.assertEqual(failed_article.sdxl_image_prompt_status, STATUS_FAILED)
        self.assertNotEqual(successful_article.sdxl_image_prompt, "")

    @staticmethod
    def build_article(article_id: int) -> Article:
        article = Article(
            id=article_id,
            category="경제(KR)",
            title="반도체 생산시설 투자",
            source="테스트 언론사",
            google_link=f"https://example.com/article-{article_id}",
        )
        article.instagram_caption = "반도체 생산시설 투자가 확대됐습니다."
        article.body = "기업이 국내 반도체 생산시설에 투자합니다."
        return article


if __name__ == "__main__":
    unittest.main()
