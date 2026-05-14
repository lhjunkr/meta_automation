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

# 전체 파이프라인 개요
# 1. Google News 후보를 수집하고 history.jsonl 기준으로 이미 사용한 기사를 제외합니다.
# 2. Gemini가 카테고리별 1순위/2순위 기사를 고릅니다.
# 3. 선택 기사 링크를 원문 URL로 정화하고 본문을 추출합니다.
# 4. 인스타 캡션, 이미지 프롬프트, 포스터 이미지를 생성합니다.
# 5. 최종 이미지를 Cloudflare R2에 올리고, 설정된 Meta API로 인스타/페이스북에 게시합니다.

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 수집 정책. 운영 기준상 제외할 언론사명/도메인 키워드를 관리합니다.
EXCLUDED_SOURCE_KEYWORDS = [
    "한겨레",
    "hankyoreh",
    "경향",
    "khan",
    "내일신문",
    "naeil",
    "mbc",
    "문화방송",
    "뉴스타파",
    "newstapa",
    "미디어오늘",
    "mediatoday",
    "오마이뉴스",
    "ohmynews",
    "프레시안",
    "pressian",
]

# 수집한 기사 출처가 제외 키워드에 해당하는지 확인합니다.
def is_excluded_source(source):
    normalized_source = source.lower()
    return any(keyword.lower() in normalized_source for keyword in EXCLUDED_SOURCE_KEYWORDS)

# Step 0-1. 오늘 날짜 기준 실행 폴더와 이미지 저장 폴더를 준비합니다.
def create_run_dir():
    today = datetime.now().strftime("%Y-%m-%d")
    run_dir = Path("outputs") / today
    image_dir = run_dir / "images"

    image_dir.mkdir(parents=True, exist_ok=True)

    return run_dir

# Step 0-2. history.jsonl에서 이미 사용한 기사 링크를 읽어 중복 후보를 제외합니다.
def load_seen_links():
    seen_links = set()
    history_path = Path("history.jsonl")

    if not history_path.exists():
        print("기록된 뉴스가 없습니다.")
        return seen_links

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            google_link = record.get("google_link")
            if google_link:
                seen_links.add(google_link)

    print(f"기록된 뉴스 {len(seen_links)}건을 블랙리스트에 선탑재했습니다.")
    return seen_links

# Step 1. Google News에서 카테고리별 후보 기사를 수집합니다.
def fetch_top_news():
    print("[Step 1] 글로벌 구글 뉴스 데이터 수집...")

    seen_links = load_seen_links()

    gn_kr = GoogleNews(lang="ko", country="KR")
    gn_us = GoogleNews(lang="en", country="US")
    raw_news = []

    def add_news(entries, category_name):
        added_count = 0

        for entry in entries:
            if entry.link in seen_links:
                continue

            source = ""
            if hasattr(entry, "source") and entry.source:
                source = entry.source.get("title", "")

            if is_excluded_source(source):
                print(f" -> 제외 언론사 스킵: {source}")
                continue


            raw_news.append(
                {
                    "id": len(raw_news) + 1,
                    "category": category_name,
                    "title": entry.title,
                    "source": source,
                    "google_link": entry.link,
                }
            )

            seen_links.add(entry.link)
            added_count += 1

            if added_count >= 10:
                break

    try:
        kr_top = gn_kr.top_news()
        print(" -> 한국 종합 헤드라인 수집 완료")
        add_news(kr_top["entries"], "종합(KR)")
    except Exception as e:
        print(f"한국 종합 뉴스 수집 실패: {e}")

    try:
        kr_biz = gn_kr.topic_headlines("BUSINESS")
        print(" -> 한국 경제 헤드라인 수집 완료")
        add_news(kr_biz["entries"], "경제(KR)")
    except Exception as e:
        print(f"한국 경제 뉴스 수집 실패: {e}")

    try:
        us_biz = gn_us.topic_headlines("BUSINESS")
        print(" -> 미국 경제 헤드라인 수집 완료")
        add_news(us_biz["entries"], "경제(US)")
    except Exception as e:
        print(f"미국 경제 뉴스 수집 실패: {e}")

    return raw_news

# Step 5-1. Google News 중계 링크를 실제 언론사 URL로 정화합니다.
def resolve_article_url(google_link):
    try:
        decoded_result = gnewsdecoder(google_link, interval=1)

        if decoded_result.get("status"):
            resolved_link = decoded_result["decoded_url"]
            print(f" -> 원문 URL: {resolved_link}")
            return resolved_link

        print(f"URL 정화 실패: {decoded_result.get('message')}")
        return ""

    except Exception as e:
        print(f"URL 정화 중 오류 발생: {e}")
        return ""


# Step 5-2. 선택된 기사들의 Google News 링크를 원문 URL로 정화합니다.
def resolve_selected_article_links(selected_articles):
    for article in selected_articles:
        print(f"URL 정화 중: {article['title'][:30]}...")
        article["resolved_link"] = resolve_article_url(article["google_link"])

    return selected_articles


# Step 6-1. 원문 URL에 접속해 기사 본문 텍스트를 추출합니다.
def fetch_article_body(resolved_link):
    try:
        response = requests.get(
            resolved_link,
            headers=REQUEST_HEADERS,
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()

    except requests.RequestException as e:
        print(f"본문 페이지 다운로드 실패: {resolved_link} ({e})")
        return "", "download_failed"

    try:
        body = trafilatura.extract(
            response.text,
            url=resolved_link,
            include_comments=False,
            include_tables=False,
        )
    except Exception as extraction_error:
        print(f"본문 추출 실패: {resolved_link} ({extraction_error})")
        return "", "body_extract_failed"

    body = body or ""

    if len(body.strip()) < 300:
        print(" -> 본문 추출 실패 또는 본문이 너무 짧습니다.")
        return body, "extract_failed"

    print(f" -> 본문 추출 완료: {len(body.strip())}자")
    return body, "success"


# Step 6-2. 선택된 기사들의 본문을 수집하고 처리 상태를 저장합니다.
def fetch_selected_article_bodies(selected_articles):
    for article in selected_articles:
        print(f"본문 수집 중: {article['title'][:30]}...")

        if not article.get("resolved_link"):
            article["body"] = ""
            article["status"] = "resolve_failed"
            print(" -> 원문 URL이 없어 본문 수집을 건너뜁니다.")
            continue

        article["body"], article["status"] = fetch_article_body(
            article["resolved_link"]
        )

    return selected_articles

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

    today = datetime.now().date()

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
