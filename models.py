from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Article:
    id: int
    category: str
    title: str
    source: str
    google_link: str

    selection_rank: str = ""
    backup_article: Article | None = None

    resolved_link: str = ""
    body: str = ""
    status: str = ""

    instagram_caption_raw: str = ""
    instagram_caption: str = ""
    instagram_caption_status: str = ""

    sdxl_image_prompt_raw: str = ""
    sdxl_image_prompt: str = ""
    sdxl_image_prompt_status: str = ""

    image_path: str = ""
    image_generation_status: str = ""
    image_generation_model: str = ""
    image_generation_error: str = ""

    final_image_path: str = ""
    image_overlay_status: str = ""

    public_image_url: str = ""
    r2_upload_status: str = ""

    instagram_publish_status: str = ""
    instagram_post_id: str = ""
    instagram_publish_error: str = ""

    facebook_publish_status: str = ""
    facebook_post_id: str = ""
    facebook_publish_error: str = ""

    publish_status: str = ""

    # Preserve unknown runtime fields so older artifacts can round-trip during schema changes.
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, article_data: dict[str, Any]) -> Article:
        known_field_names = {
            field_name
            for field_name in cls.__dataclass_fields__
            if field_name != "extra_fields"
        }

        backup_article_data = article_data.get("backup_article")
        backup_article = (
            cls.from_dict(backup_article_data)
            if isinstance(backup_article_data, dict)
            else None
        )

        extra_fields = {
            key: value
            for key, value in article_data.items()
            if key not in known_field_names
        }

        return cls(
            id=article_data["id"],
            category=article_data["category"],
            title=article_data["title"],
            source=article_data.get("source", ""),
            google_link=article_data["google_link"],
            selection_rank=article_data.get("selection_rank", ""),
            backup_article=backup_article,
            resolved_link=article_data.get("resolved_link", ""),
            body=article_data.get("body", ""),
            status=article_data.get("status", ""),
            instagram_caption_raw=article_data.get("instagram_caption_raw", ""),
            instagram_caption=article_data.get("instagram_caption", ""),
            instagram_caption_status=article_data.get("instagram_caption_status", ""),
            sdxl_image_prompt_raw=article_data.get("sdxl_image_prompt_raw", ""),
            sdxl_image_prompt=article_data.get("sdxl_image_prompt", ""),
            sdxl_image_prompt_status=article_data.get("sdxl_image_prompt_status", ""),
            image_path=article_data.get("image_path", ""),
            image_generation_status=article_data.get("image_generation_status", ""),
            image_generation_model=article_data.get("image_generation_model", ""),
            image_generation_error=article_data.get("image_generation_error", ""),
            final_image_path=article_data.get("final_image_path", ""),
            image_overlay_status=article_data.get("image_overlay_status", ""),
            public_image_url=article_data.get("public_image_url", ""),
            r2_upload_status=article_data.get("r2_upload_status", ""),
            instagram_publish_status=article_data.get("instagram_publish_status", ""),
            instagram_post_id=article_data.get("instagram_post_id", ""),
            instagram_publish_error=article_data.get("instagram_publish_error", ""),
            facebook_publish_status=article_data.get("facebook_publish_status", ""),
            facebook_post_id=article_data.get("facebook_post_id", ""),
            facebook_publish_error=article_data.get("facebook_publish_error", ""),
            publish_status=article_data.get("publish_status", ""),
            extra_fields=extra_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        article_data = dict(self.extra_fields)

        article_data.update(
            {
                "id": self.id,
                "category": self.category,
                "title": self.title,
                "source": self.source,
                "google_link": self.google_link,
                "selection_rank": self.selection_rank,
                "backup_article": (
                    self.backup_article.to_dict()
                    if self.backup_article
                    else None
                ),
                "resolved_link": self.resolved_link,
                "body": self.body,
                "status": self.status,
                "instagram_caption_raw": self.instagram_caption_raw,
                "instagram_caption": self.instagram_caption,
                "instagram_caption_status": self.instagram_caption_status,
                "sdxl_image_prompt_raw": self.sdxl_image_prompt_raw,
                "sdxl_image_prompt": self.sdxl_image_prompt,
                "sdxl_image_prompt_status": self.sdxl_image_prompt_status,
                "image_path": self.image_path,
                "image_generation_status": self.image_generation_status,
                "image_generation_model": self.image_generation_model,
                "image_generation_error": self.image_generation_error,
                "final_image_path": self.final_image_path,
                "image_overlay_status": self.image_overlay_status,
                "public_image_url": self.public_image_url,
                "r2_upload_status": self.r2_upload_status,
                "instagram_publish_status": self.instagram_publish_status,
                "instagram_post_id": self.instagram_post_id,
                "instagram_publish_error": self.instagram_publish_error,
                "facebook_publish_status": self.facebook_publish_status,
                "facebook_post_id": self.facebook_post_id,
                "facebook_publish_error": self.facebook_publish_error,
                "publish_status": self.publish_status,
            }
        )

        return article_data


def articles_from_dicts(article_data_list: list[dict[str, Any]]) -> list[Article]:
    return [Article.from_dict(article_data) for article_data in article_data_list]


def articles_to_dicts(articles: list[Article]) -> list[dict[str, Any]]:
    return [article.to_dict() for article in articles]
