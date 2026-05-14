import os
import base64
import requests
import trafilatura
import json
import shutil
import boto3
import random
import time
import re

# pygooglenews still imports feedparser 5.x, which expects this Python 2-era alias.
# Define it before pygooglenews imports feedparser so GitHub Actions can run on Python 3.11.
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

from dotenv import load_dotenv
from google import genai
from google.genai import types
from googlenewsdecoder import gnewsdecoder
from pygooglenews import GoogleNews
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from huggingface_hub import InferenceClient
from botocore.exceptions import ClientError
from config import get_int_env, is_dry_run
from history import append_publish_history, count_today_published, is_already_published
from publishing import publish_to_social_channels
from content import (
    select_best_articles,
    match_selected_articles,
    generate_instagram_captions,
    generate_sdxl_image_prompts,
)
from image_generation import generate_huggingface_images
from image_rendering import render_news_image_overlays
from storage import upload_article_images_to_r2
from outputs import (
    create_run_dir,
    save_instagram_captions,
    save_sdxl_image_prompts,
    save_failed_categories,
    save_generated_images,
    save_selected_news,
    save_selected_articles,
    cleanup_old_outputs,
)
from news import fetch_top_news, resolve_selected_article_links, fetch_selected_article_bodies

# Step 10-1. 본문, 캡션, 이미지, R2 업로드까지 성공했는지 검사합니다.
def is_article_complete(article):
    return (
        article.get("status") == "success"
        and article.get("instagram_caption_status") == "success"
        and article.get("sdxl_image_prompt_status") == "success"
        and article.get("image_generation_status") == "success"
        and article.get("image_overlay_status") == "success"
        and article.get("r2_upload_status") == "success"
        and bool(article.get("final_image_path"))
        and bool(article.get("public_image_url"))
    )

# Step 10-2. 선택 기사에 대해 본문 수집부터 R2 업로드까지 콘텐츠 생성 흐름을 실행합니다.
def process_content_pipeline(selected_articles, run_dir):
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

# Step 10-3. 1순위 기사 처리 실패 시 같은 카테고리의 2순위 기사로 재시도합니다.
def retry_failed_categories_with_backup(selected_articles, run_dir):
    final_articles = []
    failed_categories = []

    for article in selected_articles:
        if is_article_complete(article):
            final_articles.append(article)
            continue

        backup_article = article.get("backup_article")

        if not backup_article:
            failed_categories.append(
                {
                    "category": article.get("category", ""),
                    "primary_id": article.get("id", ""),
                    "backup_id": "",
                    "reason": "primary_failed_no_backup",
                }
            )
            continue

        print(f"1순위 실패, 2순위 기사로 재시도: {article['category']}")

        backup_article["selection_rank"] = "backup"
        backup_article["backup_article"] = None

        processed_backup = process_content_pipeline([backup_article], run_dir)[0]

        if is_article_complete(processed_backup):
            final_articles.append(processed_backup)
        else:
            failed_categories.append(
                {
                    "category": article.get("category", ""),
                    "primary_id": article.get("id", ""),
                    "backup_id": backup_article.get("id", ""),
                    "reason": "primary_and_backup_failed",
                }
            )

    save_failed_categories(failed_categories, run_dir)

    return final_articles

# Step 13-3. 소셜 업로드 성공 후 history 기록과 오래된 outputs 정리를 수행합니다.
def handle_publish_success(published_articles):
    append_publish_history(published_articles, status="published")
    cleanup_old_outputs(keep_days=3)

# Main. 전체 콘텐츠 생성 파이프라인을 실행합니다.
if __name__ == "__main__":
    # 실행 폴더를 만든 뒤 오늘 사용할 뉴스 후보를 수집합니다.
    run_dir = create_run_dir()
    news_list = fetch_top_news()

    for news in news_list[:3]:
        print(news)

    print(f"\n필터링 완료. 총 {len(news_list)}개의 신선한 뉴스를 확보했습니다.\n")

    if len(news_list) > 0:
        print("--- [Gemini 선정 결과] ---")
        selected_result = select_best_articles(news_list)
        print(selected_result)

        with open(run_dir / "gemini_selected_result.txt", "w", encoding="utf-8") as f:
            f.write(selected_result)

        # Gemini가 고른 ID를 원본 기사 데이터와 매칭한 뒤 콘텐츠 생성 파이프라인을 실행합니다.
        selected_articles = match_selected_articles(selected_result, news_list)

        selected_articles = process_content_pipeline(selected_articles, run_dir)
        selected_articles = retry_failed_categories_with_backup(selected_articles, run_dir)

        # 최종 산출물을 파일로 저장합니다.
        save_selected_news(selected_articles, run_dir)
        save_selected_articles(selected_articles, run_dir)

        if is_dry_run():
            print("[DRY_RUN] 실제 인스타그램/페이스북 업로드를 건너뜁니다.")
            published_articles = []
        else:
            published_articles = publish_to_social_channels(selected_articles)
            handle_publish_success(published_articles)


        print("\n[완료] 오늘 콘텐츠 생성 파이프라인이 끝났습니다.")
        print(f"산출물 저장 위치: {run_dir}")

    else:
        print("수집된 뉴스가 없습니다. 구글 뉴스 연결 상태를 확인하세요.")
