import unittest

from image_rendering import clean_article_title


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


if __name__ == "__main__":
    unittest.main()