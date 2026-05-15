import os
import random
import time

import requests
from dotenv import load_dotenv

from config import get_int_env
from constants import (
    PUBLISH_STATUS_SKIPPED_ALREADY_PUBLISHED,
    PUBLISH_STATUS_SKIPPED_NO_PUBLIC_IMAGE_URL,
    STATUS_FAILED,
    STATUS_PUBLISHED,
    STATUS_SUCCESS,
)
from history import count_today_published, is_already_published
from models import Article

GRAPH_API_VERSION = "v19.0"


def validate_meta_config() -> None:
    load_dotenv()

    required_keys = [
        "META_ACCESS_TOKEN",
        "IG_USER_ID",
        "FACEBOOK_PAGE_ID",
        "FACEBOOK_PAGE_ACCESS_TOKEN",
    ]

    missing_keys = [key for key in required_keys if not os.getenv(key)]

    if missing_keys:
        raise RuntimeError(
            ".env에 Meta 업로드 설정이 없습니다: " + ", ".join(missing_keys)
        )


def fetch_meta_graph_object(object_id: str, access_token: str, fields: str) -> dict:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{object_id}"

    response = requests.get(
        url,
        params={
            "fields": fields,
            "access_token": access_token,
        },
        timeout=30,
    )

    data = response.json()

    if response.status_code >= 400:
        raise RuntimeError(f"Meta Graph API 검증 실패: {data}")

    return data


def preflight_meta_publishing() -> dict:
    load_dotenv()
    validate_meta_config()

    meta_access_token = os.getenv("META_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    facebook_page_id = os.getenv("FACEBOOK_PAGE_ID")
    facebook_page_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    if (
        not meta_access_token
        or not ig_user_id
        or not facebook_page_id
        or not facebook_page_access_token
    ):
        raise RuntimeError("Meta preflight에 필요한 환경변수가 없습니다.")

    print("Meta preflight 검증 중...")

    instagram_account = fetch_meta_graph_object(
        ig_user_id,
        meta_access_token,
        "id,username",
    )
    print(f" -> Instagram 계정 확인: {instagram_account.get('id')}")

    facebook_page = fetch_meta_graph_object(
        facebook_page_id,
        facebook_page_access_token,
        "id,name",
    )
    print(f" -> Facebook 페이지 확인: {facebook_page.get('name')}")

    return {
        "instagram_account_id": instagram_account.get("id", ""),
        "facebook_page_id": facebook_page.get("id", ""),
        "facebook_page_name": facebook_page.get("name", ""),
    }


def create_instagram_media_container(article: Article):
    load_dotenv()

    access_token = os.getenv("META_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")

    image_url = article.public_image_url
    caption = article.instagram_caption

    if not image_url:
        raise RuntimeError("public_image_url이 없어 Instagram 컨테이너를 만들 수 없습니다.")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}/media"

    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or "id" not in data:
        raise RuntimeError(f"Instagram 컨테이너 생성 실패: {data}")

    return data["id"]


def publish_instagram_media(creation_id: str) -> str:
    load_dotenv()

    access_token = os.getenv("META_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}/media_publish"

    payload = {
        "creation_id": creation_id,
        "access_token": access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or "id" not in data:
        raise RuntimeError(f"Instagram 게시 실패: {data}")

    return data["id"]


def publish_article_to_instagram(article: Article) -> Article:
    try:
        creation_id = create_instagram_media_container(article)
        instagram_post_id = publish_instagram_media(creation_id)

        article.instagram_publish_status = STATUS_SUCCESS
        article.instagram_post_id = instagram_post_id
        article.instagram_publish_error = ""

        print(f" -> Instagram 게시 완료: {instagram_post_id}")

    except Exception as e:
        article.instagram_publish_status = STATUS_FAILED
        article.instagram_post_id = ""
        article.instagram_publish_error = str(e)

        print(f" -> Instagram 게시 실패: {e}")

    return article


def publish_article_to_facebook_page(article: Article) -> Article:
    load_dotenv()

    page_id = os.getenv("FACEBOOK_PAGE_ID")
    page_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    image_url = article.public_image_url
    caption = article.instagram_caption

    if not image_url:
        article.facebook_publish_status = STATUS_FAILED
        article.facebook_post_id = ""
        article.facebook_publish_error = "public_image_url이 없어 Facebook에 게시할 수 없습니다."
        return article

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"

    payload = {
        "url": image_url,
        "caption": caption,
        "access_token": page_access_token,
        "published": "true",
    }

    try:
        response = requests.post(url, data=payload, timeout=30)
        data = response.json()

        if response.status_code >= 400 or "id" not in data:
            raise RuntimeError(f"Facebook 게시 실패: {data}")

        article.facebook_publish_status = STATUS_SUCCESS
        article.facebook_post_id = data["id"]
        article.facebook_publish_error = ""

        print(f" -> Facebook 게시 완료: {data['id']}")

    except Exception as e:
        article.facebook_publish_status = STATUS_FAILED
        article.facebook_post_id = ""
        article.facebook_publish_error = str(e)

        print(f" -> Facebook 게시 실패: {e}")

    return article


def get_publish_delay_seconds(publish_index: int) -> int:
    upload_window_minutes = get_int_env("UPLOAD_WINDOW_MINUTES", 120)
    post_spacing_minutes = get_int_env("POST_SPACING_MINUTES", 10)
    max_daily_posts = get_int_env("MAX_DAILY_POSTS", 3)

    latest_first_post_minute = upload_window_minutes - (
        (max_daily_posts - 1) * post_spacing_minutes
    )
    latest_first_post_minute = max(latest_first_post_minute, 0)

    first_post_delay_seconds = random.randint(
        0,
        latest_first_post_minute * 60,
    )

    return first_post_delay_seconds + (
        publish_index * post_spacing_minutes * 60
    )


def publish_to_social_channels(selected_articles: list[Article]) -> list[Article]:
    preflight_meta_publishing()

    published_articles: list[Article] = []
    max_daily_posts = get_int_env("MAX_DAILY_POSTS", 3)
    already_published_today = count_today_published()
    remaining_slots = max_daily_posts - already_published_today

    if remaining_slots <= 0:
        print(f"오늘 업로드 한도({max_daily_posts}개)에 도달했습니다.")
        return published_articles

    publish_attempt_index = 0

    for article in selected_articles:
        if len(published_articles) >= remaining_slots:
            break

        if not article.public_image_url:
            article.publish_status = PUBLISH_STATUS_SKIPPED_NO_PUBLIC_IMAGE_URL
            print(" -> public_image_url이 없어 게시를 건너뜁니다.")
            continue

        if is_already_published(article):
            article.publish_status = PUBLISH_STATUS_SKIPPED_ALREADY_PUBLISHED
            print(" -> 이미 게시된 기사라 건너뜁니다.")
            continue

        delay_seconds = get_publish_delay_seconds(publish_attempt_index)

        if delay_seconds > 0:
            delay_minutes = round(delay_seconds / 60, 1)
            print(f"게시 전 대기: {delay_minutes}분")
            time.sleep(delay_seconds)

        publish_attempt_index += 1

        publish_article_to_instagram(article)
        publish_article_to_facebook_page(article)

        if (
            article.instagram_publish_status == STATUS_SUCCESS
            and article.facebook_publish_status == STATUS_SUCCESS
        ):
            article.publish_status = STATUS_PUBLISHED
            published_articles.append(article)
        else:
            article.publish_status = STATUS_FAILED

    return published_articles
