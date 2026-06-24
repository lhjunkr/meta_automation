from constants import STATUS_FAILED, STATUS_PUBLISHED, STATUS_SUCCESS
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

        # backup 기사가 또 다른 fallback을 들고 있으면 실패 카테고리가
        # 의도치 않은 후보로 재귀될 수 있으므로 여기서 끊습니다.
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
    # 최종 게시 후보에서 빠진 카테고리 실패도 이메일 리포트에 포함합니다.
    save_failure_report(final_articles, run_dir, failed_categories)

    return final_articles


def has_required_channel_publish_success(article: Article) -> bool:
    # Instagram/Facebook은 핵심 게시 채널이고, Threads는 장애가 나도 보조 채널 실패로만 기록합니다.
    return (
        article.instagram_publish_status == STATUS_SUCCESS
        and article.facebook_publish_status == STATUS_SUCCESS
    )


def has_any_channel_publish_success(article: Article) -> bool:
    return (
        article.instagram_publish_status == STATUS_SUCCESS
        or article.facebook_publish_status == STATUS_SUCCESS
        or article.threads_publish_status == STATUS_SUCCESS
    )


def count_required_channel_publish_successes(selected_articles: list[Article]) -> dict[str, int]:
    return {
        "Instagram": sum(
            1
            for article in selected_articles
            if article.instagram_publish_status == STATUS_SUCCESS
        ),
        "Facebook": sum(
            1
            for article in selected_articles
            if article.facebook_publish_status == STATUS_SUCCESS
        ),
    }


def ensure_required_social_channels_published(selected_articles: list[Article]) -> None:
    required_channel_counts = count_required_channel_publish_successes(selected_articles)
    failed_channels = [
        f"{channel_name}=0"
        for channel_name, publish_count in required_channel_counts.items()
        if publish_count == 0
    ]

    if failed_channels:
        raise RuntimeError(
            "Required social channel publishing failed: "
            + ", ".join(failed_channels)
        )


def handle_publish_results(selected_articles: list[Article]) -> None:
    published_articles = [
        article for article in selected_articles if has_required_channel_publish_success(article)
    ]
    partially_published_articles = [
        article
        for article in selected_articles
        if has_any_channel_publish_success(article)
        and not has_required_channel_publish_success(article)
    ]

    if published_articles:
        append_publish_history(published_articles, status=STATUS_PUBLISHED)

    if partially_published_articles:
        # 일부 채널이라도 실제 게시가 끝난 기사는 다음 실행에서 중복 게시되지 않도록 이력에 남깁니다.
        append_publish_history(partially_published_articles, status=STATUS_FAILED)

    cleanup_old_outputs(keep_days=3)
