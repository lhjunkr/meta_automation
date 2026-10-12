import os

import requests
from dotenv import load_dotenv

from constants import STATUS_FAILED, STATUS_SUCCESS
from models import Article

GRAPH_API_VERSION = "v19.0"


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

    # Facebook Page 게시에는 IG 토큰이 아니라 Page 권한이 붙은 access token을 사용해야 합니다.
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


def upload_unpublished_facebook_photo(image_url: str) -> str:
    load_dotenv()

    page_id = os.getenv("FACEBOOK_PAGE_ID")
    page_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"

    # 페이지 스토리는 피드에 노출되지 않은 사진 ID로만 만들 수 있어 published=false로 먼저 올립니다.
    payload = {
        "url": image_url,
        "access_token": page_access_token,
        "published": "false",
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or "id" not in data:
        raise RuntimeError(f"Facebook 스토리 사진 업로드 실패: {data}")

    return data["id"]


def publish_facebook_photo_story(photo_id: str) -> str:
    load_dotenv()

    page_id = os.getenv("FACEBOOK_PAGE_ID")
    page_access_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photo_stories"

    payload = {
        "photo_id": photo_id,
        "access_token": page_access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or not data.get("success") or "post_id" not in data:
        raise RuntimeError(f"Facebook 스토리 게시 실패: {data}")

    return data["post_id"]


def publish_article_story_to_facebook_page(article: Article) -> Article:
    image_url = article.public_story_image_url

    if not image_url:
        article.facebook_story_status = STATUS_FAILED
        article.facebook_story_id = ""
        article.facebook_story_error = "public_story_image_url이 없어 Facebook 스토리를 게시할 수 없습니다."
        return article

    try:
        photo_id = upload_unpublished_facebook_photo(image_url)
        facebook_story_id = publish_facebook_photo_story(photo_id)

        article.facebook_story_status = STATUS_SUCCESS
        article.facebook_story_id = facebook_story_id
        article.facebook_story_error = ""

        print(f" -> Facebook 스토리 게시 완료: {facebook_story_id}")

    except Exception as e:
        article.facebook_story_status = STATUS_FAILED
        article.facebook_story_id = ""
        article.facebook_story_error = str(e)

        print(f" -> Facebook 스토리 게시 실패: {e}")

    return article
