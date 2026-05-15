from constants import STATUS_PUBLISHED, STATUS_SUCCESS
from content import generate_instagram_captions, generate_sdxl_image_prompts
from history import append_publish_history
from image_generation import generate_huggingface_images
from image_rendering import render_news_image_overlays
from models import Article
from news import fetch_selected_article_bodies, resolve_selected_article_links
from outputs import (
    cleanup_old_outputs,
    save_failed_categories,
    save_failure_report,
    save_generated_images,
    save_instagram_captions,
    save_sdxl_image_prompts,
)
from storage import upload_article_images_to_r2


def is_article_complete(article: Article) -> bool:
    return (
        article.status == STATUS_SUCCESS
        and article.instagram_caption_status == STATUS_SUCCESS
        and article.sdxl_image_prompt_status == STATUS_SUCCESS
        and article.image_generation_status == STATUS_SUCCESS
        and article.image_overlay_status == STATUS_SUCCESS
        and article.r2_upload_status == STATUS_SUCCESS
        and bool(article.final_image_path)
        and bool(article.public_image_url)
    )

def process_content_pipeline(selected_articles: list[Article], run_dir) -> list[Article]:
    selected_articles = resolve_selected_article_links(selected_articles)
    selected_articles = fetch_selected_article_bodies(selected_articles)

    selected_articles = generate_instagram_captions(selected_articles)
    save_instagram_captions(selected_articles, run_dir)

    selected_articles = generate_sdxl_image_prompts(selected_articles)
    save_sdxl_image_prompts(selected_articles, run_dir)

    selected_articles = generate_huggingface_images(selected_articles, run_dir)
    selected_articles = render_news_image_overlays(selected_articles)
    selected_articles = upload_article_images_to_r2(selected_articles, run_dir)
    save_generated_images(selected_articles, run_dir)

    return selected_articles


def retry_failed_categories_with_backup(selected_articles: list[Article], run_dir) -> list[Article]:
    final_articles = []
    failed_categories = []

    for article in selected_articles:
        if is_article_complete(article):
            final_articles.append(article)
            continue

        backup_article = article.backup_article

        if not backup_article:
            failed_categories.append(
                {
                    "category": article.category,
                    "primary_id": article.id,
                    "backup_id": "",
                    "reason": "primary_failed_no_backup",
                }
            )
            continue

        print(f"1순위 실패, 2순위 기사로 재시도: {article.category}")

        # Backups must not carry their own fallback article, otherwise a bad category
        # can recurse through unintended candidates instead of failing clearly.
        backup_article.selection_rank = "backup"
        backup_article.backup_article = None

        processed_backup = process_content_pipeline([backup_article], run_dir)[0]

        if is_article_complete(processed_backup):
            final_articles.append(processed_backup)
        else:
            failed_categories.append(
                {
                    "category": article.category,
                    "primary_id": article.id,
                    "backup_id": backup_article.id,
                    "reason": "primary_and_backup_failed",
                }
            )

    save_failed_categories(failed_categories, run_dir)
    save_failure_report(final_articles, run_dir)

    return final_articles

def handle_publish_success(published_articles: list[Article]) -> None:
    append_publish_history(published_articles, status=STATUS_PUBLISHED)
    cleanup_old_outputs(keep_days=3)
