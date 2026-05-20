from constants import (
    PUBLISH_STATUS_SKIPPED_ALREADY_PUBLISHED,
    STATUS_PUBLISHED,
    STATUS_SUCCESS,
)
from models import Article


def build_category_failure_summary(failed_categories: list[dict]) -> list[str]:
    return [
        (
            f"category:{item.get('category', '')} "
            f"primary:{item.get('primary_id', '')} "
            f"backup:{item.get('backup_id', '')} "
            f"reason:{item.get('reason', '')}"
        )
        for item in failed_categories
    ]


def build_article_failure_summary(article: Article) -> list[str]:
    failure_reasons = []

    if article.status and article.status != STATUS_SUCCESS:
        failure_reasons.append(f"body:{article.status}")

    if (
        article.instagram_caption_status
        and article.instagram_caption_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"caption:{article.instagram_caption_status}")

    if (
        article.sdxl_image_prompt_status
        and article.sdxl_image_prompt_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"image_prompt:{article.sdxl_image_prompt_status}")

    if (
        article.image_generation_status
        and article.image_generation_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"image_generation:{article.image_generation_status}")

    if article.image_overlay_status and article.image_overlay_status != STATUS_SUCCESS:
        failure_reasons.append(f"image_overlay:{article.image_overlay_status}")

    if article.r2_upload_status and article.r2_upload_status != STATUS_SUCCESS:
        failure_reasons.append(f"r2:{article.r2_upload_status}")

    if (
        article.instagram_publish_status
        and article.instagram_publish_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"instagram:{article.instagram_publish_status}")

    if (
        article.facebook_publish_status
        and article.facebook_publish_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"facebook:{article.facebook_publish_status}")

    if (
        article.threads_publish_status
        and article.threads_publish_status != STATUS_SUCCESS
    ):
        failure_reasons.append(f"threads:{article.threads_publish_status}")

    if article.publish_status and article.publish_status not in {
        STATUS_PUBLISHED,
        PUBLISH_STATUS_SKIPPED_ALREADY_PUBLISHED,
    }:
        failure_reasons.append(f"publish:{article.publish_status}")

    return failure_reasons


def build_run_failure_report(
    selected_articles: list[Article],
    failed_categories: list[dict] | None = None,
) -> str:
    lines = ["Failure Summary", ""]

    failed_articles = []
    category_failure_reasons = build_category_failure_summary(failed_categories or [])

    if category_failure_reasons:
        lines.extend(["Category Failures", ""])

        for category_failure_reason in category_failure_reasons:
            lines.extend([category_failure_reason, ""])

        lines.extend(["Article Failures", ""])

    for article in selected_articles:
        failure_reasons = build_article_failure_summary(article)

        if not failure_reasons:
            continue

        failed_articles.append(article)

        lines.extend(
            [
                f"ID: {article.id}",
                f"Category: {article.category}",
                f"Title: {article.title}",
                f"Source: {article.source}",
                f"Reasons: {', '.join(failure_reasons)}",
                "",
            ]
        )

    if not failed_articles and not category_failure_reasons:
        return "Failure Summary\n\nNo article-level failures detected.\n"

    return "\n".join(lines).rstrip() + "\n"
