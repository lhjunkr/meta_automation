import unittest

from PIL import Image, ImageDraw

from image_rendering import clean_article_title, load_korean_font, text_width, wrap_text


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


if __name__ == "__main__":
    unittest.main()
