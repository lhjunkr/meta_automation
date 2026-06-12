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


if __name__ == "__main__":
    unittest.main()
