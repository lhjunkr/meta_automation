import unittest

from models import Article


class ArticleModelTest(unittest.TestCase):
    def test_article_roundtrip_preserves_core_fields(self):
        article = Article.from_dict(
            {
                "id": 1,
                "category": "경제(US)",
                "title": "Test title",
                "source": "Test source",
                "google_link": "https://example.com/news",
                "unknown_runtime_field": "keep-me",
                "backup_article": {
                    "id": 2,
                    "category": "경제(US)",
                    "title": "Backup title",
                    "source": "Backup source",
                    "google_link": "https://example.com/backup",
                },
            }
        )

        article_data = article.to_dict()

        self.assertEqual(article.id, 1)
        self.assertEqual(article.category, "경제(US)")
        self.assertIsNotNone(article.backup_article)
        self.assertEqual(article.backup_article.id, 2)
        self.assertEqual(article_data["unknown_runtime_field"], "keep-me")
        self.assertEqual(article_data["backup_article"]["title"], "Backup title")


if __name__ == "__main__":
    unittest.main()