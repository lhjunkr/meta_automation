import unittest

from content import MAX_IMAGE_PROMPT_BODY_CHARS, build_sdxl_image_prompt
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


if __name__ == "__main__":
    unittest.main()
