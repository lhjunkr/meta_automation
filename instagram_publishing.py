import os
import time

import requests
from dotenv import load_dotenv

from constants import STATUS_FAILED, STATUS_SUCCESS
from models import Article

GRAPH_API_VERSION = "v19.0"
INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS = 5
INSTAGRAM_CONTAINER_MAX_WAIT_SECONDS = 120


def create_instagram_media_container(article: Article) -> str:
    load_dotenv()

    access_token = os.getenv("META_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")

    image_url = article.public_image_url
    caption = article.instagram_caption

    if not image_url:
        raise RuntimeError("public_image_url이 없어 Instagram 컨테이너를 만들 수 없습니다.")

    # Instagram은 컨테이너 생성과 publish 호출이 분리되어 있어 여기서는 media ID만 만듭니다.
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


def fetch_instagram_media_container_status(creation_id: str) -> dict:
    load_dotenv()

    access_token = os.getenv("META_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{creation_id}"

    response = requests.get(
        url,
        params={
            "fields": "status_code,status",
            "access_token": access_token,
        },
        timeout=30,
    )
    data = response.json()

    if response.status_code >= 400:
        raise RuntimeError(f"Instagram 컨테이너 상태 확인 실패: {data}")

    return data


def wait_for_instagram_media_container(creation_id: str) -> None:
    waited_seconds = 0

    while waited_seconds <= INSTAGRAM_CONTAINER_MAX_WAIT_SECONDS:
        container_status = fetch_instagram_media_container_status(creation_id)
        status_code = container_status.get("status_code", "")
        status_message = container_status.get("status", "")

        print(f" -> Instagram 컨테이너 상태: {status_code or status_message}")

        if status_code == "FINISHED":
            return

        if status_code == "ERROR":
            raise RuntimeError(f"Instagram 컨테이너 처리 실패: {container_status}")

        # Instagram이 R2의 image_url을 가져가 처리할 시간을 준 뒤 publish를 호출합니다.
        time.sleep(INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS)
        waited_seconds += INSTAGRAM_CONTAINER_POLL_INTERVAL_SECONDS

    raise RuntimeError(
        "Instagram 컨테이너 준비 시간이 초과되었습니다: "
        f"{INSTAGRAM_CONTAINER_MAX_WAIT_SECONDS}초"
    )


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
        wait_for_instagram_media_container(creation_id)
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