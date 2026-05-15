import shutil
from datetime import datetime
from pathlib import Path

from models import Article
from reporting import build_run_failure_report
from time_utils import now_kst, today_kst


def create_run_dir():
    # GitHub-hosted runner는 기본 UTC이므로 산출물 폴더는 운영 기준인 KST를 따릅니다.
    today = now_kst().strftime("%Y-%m-%d")
    run_dir = Path("outputs") / today
    image_dir = run_dir / "images"

    image_dir.mkdir(parents=True, exist_ok=True)

    return run_dir


def save_instagram_captions(selected_articles: list[Article], run_dir) -> None:
    with open(run_dir / "instagram_captions.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article.id}\n")
            f.write(f"Category: {article.category}\n")
            f.write(f"Title: {article.title}\n")
            f.write(f"Source: {article.source}\n")
            f.write(f"Status: {article.instagram_caption_status}\n")
            f.write("Instagram Caption:\n")
            f.write(article.instagram_caption)
            f.write("\n\n---\n\n")


def save_sdxl_image_prompts(selected_articles: list[Article], run_dir) -> None:
    with open(run_dir / "sdxl_image_prompts.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article.id}\n")
            f.write(f"Category: {article.category}\n")
            f.write(f"Title: {article.title}\n")
            f.write(f"Source: {article.source}\n")
            f.write(f"Status: {article.sdxl_image_prompt_status}\n")
            f.write("SDXL Image Prompt:\n")
            f.write(article.sdxl_image_prompt)
            f.write("\n\n---\n\n")


def save_failed_categories(failed_categories: list[dict], run_dir) -> None:
    with open(run_dir / "failed_categories.txt", "w", encoding="utf-8") as f:
        for item in failed_categories:
            f.write(f"Category: {item['category']}\n")
            f.write(f"Primary ID: {item['primary_id']}\n")
            f.write(f"Backup ID: {item['backup_id']}\n")
            f.write(f"Reason: {item['reason']}\n")
            f.write("\n---\n\n")


def save_failure_report(selected_articles: list[Article], run_dir) -> None:
    # 실패 이메일 본문에 바로 포함할 수 있도록 요약을 텍스트 산출물로 남깁니다.
    with open(run_dir / "failure_report.txt", "w", encoding="utf-8") as f:
        f.write(build_run_failure_report(selected_articles))


def save_generated_images(selected_articles: list[Article], run_dir) -> None:
    with open(run_dir / "generated_images.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article.id}\n")
            f.write(f"Category: {article.category}\n")
            f.write(f"Title: {article.title}\n")
            f.write(f"Status: {article.image_generation_status}\n")
            f.write(f"Image Model: {article.image_generation_model}\n")
            f.write(f"Image Error: {article.image_generation_error}\n")
            f.write(f"Image Path: {article.image_path}\n")
            f.write(f"Final Image Path: {article.final_image_path}\n")
            f.write(f"Overlay Status: {article.image_overlay_status}\n")
            f.write(f"R2 Upload Status: {article.r2_upload_status}\n")
            f.write(f"Public Image URL: {article.public_image_url}\n")
            f.write("\n---\n\n")


def save_selected_news(selected_articles: list[Article], run_dir) -> None:
    with open(run_dir / "selected_news.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article.id}\n")
            f.write(f"Category: {article.category}\n")
            f.write(f"Title: {article.title}\n")
            f.write(f"Source: {article.source}\n")
            f.write(f"Google Link: {article.google_link}\n")
            f.write(f"Resolved Link: {article.resolved_link}\n")
            f.write(f"Status: {article.status}\n")
            f.write(f"Instagram Caption Status: {article.instagram_caption_status}\n")
            f.write("\n---\n\n")


def save_selected_articles(selected_articles: list[Article], run_dir) -> None:
    with open(run_dir / "selected_articles.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article.id}\n")
            f.write(f"Category: {article.category}\n")
            f.write(f"Title: {article.title}\n")
            f.write(f"Source: {article.source}\n")
            f.write(f"Google Link: {article.google_link}\n")
            f.write(f"Resolved Link: {article.resolved_link}\n")
            f.write(f"Status: {article.status}\n")
            f.write(f"Instagram Caption Status: {article.instagram_caption_status}\n")
            f.write("Body:\n")
            f.write(article.body)
            f.write("\n\nInstagram Caption:\n")
            f.write(article.instagram_caption)
            f.write("\n\nSDXL Image Prompt:\n")
            f.write(article.sdxl_image_prompt)
            f.write("\n\nGenerated Image Path:\n")
            f.write(article.image_path)
            f.write("\n\nFinal Image Path:\n")
            f.write(article.final_image_path)
            f.write("\n\nR2 Upload Status:\n")
            f.write(article.r2_upload_status)
            f.write("\n\nPublic Image URL:\n")
            f.write(article.public_image_url)
            f.write("\n\nInstagram Publish Status:\n")
            f.write(article.instagram_publish_status)
            f.write("\nInstagram Post ID:\n")
            f.write(article.instagram_post_id)
            f.write("\nInstagram Publish Error:\n")
            f.write(article.instagram_publish_error)
            f.write("\n\nFacebook Publish Status:\n")
            f.write(article.facebook_publish_status)
            f.write("\nFacebook Post ID:\n")
            f.write(article.facebook_post_id)
            f.write("\nFacebook Publish Error:\n")
            f.write(article.facebook_publish_error)
            f.write("\n\nOverall Publish Status:\n")
            f.write(article.publish_status)
            f.write("\n\n---\n\n")


def cleanup_old_outputs(keep_days: int = 3) -> None:
    outputs_dir = Path("outputs")

    if not outputs_dir.exists():
        return

    today = today_kst()

    for run_dir in outputs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        try:
            run_date = datetime.strptime(run_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue

        age_days = (today - run_date).days

        if age_days >= keep_days:
            shutil.rmtree(run_dir)
            print(f"오래된 outputs 폴더 삭제: {run_dir}")
