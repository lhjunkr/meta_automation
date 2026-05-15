import shutil
from datetime import datetime
from pathlib import Path

from time_utils import now_kst, today_kst

# Step 0-1. 오늘 날짜 기준 실행 폴더와 이미지 저장 폴더를 준비합니다.
def create_run_dir():
    today = now_kst().strftime("%Y-%m-%d")
    run_dir = Path("outputs") / today
    image_dir = run_dir / "images"

    image_dir.mkdir(parents=True, exist_ok=True)

    return run_dir

# Step 7-4. 생성된 인스타 캡션을 별도 텍스트 파일로 저장합니다.
def save_instagram_captions(selected_articles, run_dir):
    with open(run_dir / "instagram_captions.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article['id']}\n")
            f.write(f"Category: {article['category']}\n")
            f.write(f"Title: {article['title']}\n")
            f.write(f"Source: {article['source']}\n")
            f.write(f"Status: {article.get('instagram_caption_status', '')}\n")
            f.write("Instagram Caption:\n")
            f.write(article.get("instagram_caption", ""))
            f.write("\n\n---\n\n")
            
# Step 8-4. 생성된 SDXL 이미지 프롬프트를 별도 텍스트 파일로 저장합니다.
def save_sdxl_image_prompts(selected_articles, run_dir):
    with open(run_dir / "sdxl_image_prompts.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article['id']}\n")
            f.write(f"Category: {article['category']}\n")
            f.write(f"Title: {article['title']}\n")
            f.write(f"Source: {article['source']}\n")
            f.write(f"Status: {article.get('sdxl_image_prompt_status', '')}\n")
            f.write("SDXL Image Prompt:\n")
            f.write(article.get("sdxl_image_prompt", ""))
            f.write("\n\n---\n\n")
            
# Step 10-4. 1순위와 2순위가 모두 실패한 카테고리를 기록합니다.
def save_failed_categories(failed_categories, run_dir):
    with open(run_dir / "failed_categories.txt", "w", encoding="utf-8") as f:
        for item in failed_categories:
            f.write(f"Category: {item['category']}\n")
            f.write(f"Primary ID: {item['primary_id']}\n")
            f.write(f"Backup ID: {item['backup_id']}\n")
            f.write(f"Reason: {item['reason']}\n")
            f.write("\n---\n\n")

# Step 11-1. 생성 이미지, 최종 이미지, R2 공개 URL 정보를 저장합니다.
def save_generated_images(selected_articles, run_dir):
    with open(run_dir / "generated_images.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article['id']}\n")
            f.write(f"Category: {article['category']}\n")
            f.write(f"Title: {article['title']}\n")
            f.write(f"Status: {article.get('image_generation_status', '')}\n")
            f.write(f"Image Path: {article.get('image_path', '')}\n")
            f.write(f"Final Image Path: {article.get('final_image_path', '')}\n")
            f.write(f"Overlay Status: {article.get('image_overlay_status', '')}\n")
            f.write(f"R2 Upload Status: {article.get('r2_upload_status', '')}\n")
            f.write(f"Public Image URL: {article.get('public_image_url', '')}\n")
            f.write("\n---\n\n")

# Step 12-1. 최종 선택 기사 메타데이터를 실행 폴더에 저장합니다.
def save_selected_news(selected_articles, run_dir):
    with open(run_dir / "selected_news.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article['id']}\n")
            f.write(f"Category: {article['category']}\n")
            f.write(f"Title: {article['title']}\n")
            f.write(f"Source: {article['source']}\n")
            f.write(f"Google Link: {article['google_link']}\n")
            f.write(f"Resolved Link: {article.get('resolved_link', '')}\n")
            f.write(f"Status: {article.get('status', '')}\n")
            f.write(f"Instagram Caption Status: {article.get('instagram_caption_status', '')}\n")
            f.write("\n---\n\n")


# Step 12-2. 본문, 캡션, 이미지 경로, 게시 상태까지 상세 결과를 저장합니다.
def save_selected_articles(selected_articles, run_dir):
    with open(run_dir / "selected_articles.txt", "w", encoding="utf-8") as f:
        for article in selected_articles:
            f.write(f"ID: {article['id']}\n")
            f.write(f"Category: {article['category']}\n")
            f.write(f"Title: {article['title']}\n")
            f.write(f"Source: {article['source']}\n")
            f.write(f"Google Link: {article['google_link']}\n")
            f.write(f"Resolved Link: {article.get('resolved_link', '')}\n")
            f.write(f"Status: {article.get('status', '')}\n")
            f.write(f"Instagram Caption Status: {article.get('instagram_caption_status', '')}\n")
            f.write("Body:\n")
            f.write(article.get("body", ""))
            f.write("\n\nInstagram Caption:\n")
            f.write(article.get("instagram_caption", ""))
            f.write("\n\nSDXL Image Prompt:\n")
            f.write(article.get("sdxl_image_prompt", ""))
            f.write("\n\nGenerated Image Path:\n")
            f.write(article.get("image_path", ""))
            f.write("\n\nFinal Image Path:\n")
            f.write(article.get("final_image_path", ""))
            f.write("\n\nR2 Upload Status:\n")
            f.write(article.get("r2_upload_status", ""))
            f.write("\n\nPublic Image URL:\n")
            f.write(article.get("public_image_url", ""))
            f.write("\n\nInstagram Publish Status:\n")
            f.write(article.get("instagram_publish_status", ""))
            f.write("\nInstagram Post ID:\n")
            f.write(article.get("instagram_post_id", ""))
            f.write("\nInstagram Publish Error:\n")
            f.write(article.get("instagram_publish_error", ""))
            f.write("\n\nFacebook Publish Status:\n")
            f.write(article.get("facebook_publish_status", ""))
            f.write("\nFacebook Post ID:\n")
            f.write(article.get("facebook_post_id", ""))
            f.write("\nFacebook Publish Error:\n")
            f.write(article.get("facebook_publish_error", ""))

            f.write("\n\nOverall Publish Status:\n")
            f.write(article.get("publish_status", ""))

            f.write("\n\n---\n\n")

# Step 13-2. outputs 폴더에서 보관 기간이 지난 실행 결과를 삭제합니다.
def cleanup_old_outputs(keep_days=3):
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