import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from image_rendering import (
    STORY_IMAGE_SIZE,
    build_story_image,
    clean_article_title,
    load_korean_font,
    render_story_image,
    text_width,
    wrap_text,
)
from models import Article


class ImageRenderingTest(unittest.TestCase):
    def test_clean_article_title_removes_unsupported_symbols(self):
        self.assertEqual(
            clean_article_title("🚨 국제 에너지 이슈"),
            "국제 에너지 이슈",
        )

    def test_clean_article_title_removes_source_suffix(self):
        self.assertEqual(
            clean_article_title("국제 에너지 이슈 - OilPrice.com"),
            "국제 에너지 이슈",
        )

    def test_wrap_text_splits_long_word_to_fit_max_width(self):
        image = Image.new("RGB", (400, 200))
        draw = ImageDraw.Draw(image)
        font = load_korean_font(32, bold=True)
        max_width = 160

        lines = wrap_text(
            draw,
            "초장문제목초장문제목초장문제목초장문제목",
            font,
            max_width=max_width,
            max_lines=3,
        )

        self.assertGreater(len(lines), 1)
        self.assertTrue(
            all(text_width(draw, line, font) <= max_width for line in lines)
        )


    def test_build_story_image_uses_story_ratio_and_keeps_poster_centered(self):
        poster = Image.new("RGB", (1024, 1280), (255, 0, 0))

        story = build_story_image(poster)

        self.assertEqual(story.size, STORY_IMAGE_SIZE)
        center_pixel = story.getpixel((540, 960))
        self.assertEqual(center_pixel, (255, 0, 0))

    def test_render_story_image_saves_jpeg_next_to_final_image(self):
        with TemporaryDirectory() as temp_dir:
            final_path = Path(temp_dir) / "article_1_final.png"
            Image.new("RGB", (1024, 1280), (0, 0, 255)).save(final_path)

            article = Article(
                id=1,
                category="경제(KR)",
                title="Test title",
                source="Test source",
                google_link="https://example.com/news",
            )
            article.final_image_path = str(final_path)

            render_story_image(article)

            story_path = Path(article.story_image_path)
            self.assertEqual(story_path.name, "article_1_story.jpg")
            with Image.open(story_path) as story_image:
                self.assertEqual(story_image.format, "JPEG")
                self.assertEqual(story_image.size, STORY_IMAGE_SIZE)

    def test_render_story_image_skips_without_final_image(self):
        article = Article(
            id=1,
            category="경제(KR)",
            title="Test title",
            source="Test source",
            google_link="https://example.com/news",
        )

        render_story_image(article)

        self.assertEqual(article.story_image_path, "")


if __name__ == "__main__":
    unittest.main()
