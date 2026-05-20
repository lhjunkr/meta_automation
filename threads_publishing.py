import os
import time

import requests
from dotenv import load_dotenv

from constants import STATUS_FAILED, STATUS_SUCCESS
from models import Article

THREADS_API_VERSION = "v1.0"
THREADS_API_BASE_URL = f"https://graph.threads.net/{THREADS_API_VERSION}"
THREADS_CONTAINER_POLL_INTERVAL_SECONDS = 5
THREADS_CONTAINER_MAX_WAIT_SECONDS = 120


def create_threads_media_container(article: Article) -> str:
    load_dotenv()

    threads_access_token = os.getenv("THREADS_ACCESS_TOKEN")
    threads_user_id = os.getenv("THREADS_USER_ID")

    image_url = article.public_image_url
    caption = article.instagram_caption

    if not image_url:
        raise RuntimeError("public_image_url이 없어 Threads 컨테이너를 만들 수 없습니다.")

    url = f"{THREADS_API_BASE_URL}/{threads_user_id}/threads"

    payload = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "text": caption,
        "access_token": threads_access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or "id" not in data:
        raise RuntimeError(f"Threads 컨테이너 생성 실패: {data}")

    return data["id"]


def fetch_threads_media_container_status(creation_id: str) -> dict:
    load_dotenv()

    threads_access_token = os.getenv("THREADS_ACCESS_TOKEN")

    url = f"{THREADS_API_BASE_URL}/{creation_id}"

    response = requests.get(
        url,
        params={
            "fields": "status,error_message",
            "access_token": threads_access_token,
        },
        timeout=30,
    )
    data = response.json()

    if response.status_code >= 400:
        raise RuntimeError(f"Threads 컨테이너 상태 확인 실패: {data}")

    return data


def wait_for_threads_media_container(creation_id: str) -> None:
    waited_seconds = 0

    while waited_seconds <= THREADS_CONTAINER_MAX_WAIT_SECONDS:
        container_status = fetch_threads_media_container_status(creation_id)
        status = container_status.get("status", "")
        error_message = container_status.get("error_message", "")

        print(f" -> Threads 컨테이너 상태: {status}")

        if status == "FINISHED":
            return

        if status == "ERROR":
            raise RuntimeError(f"Threads 컨테이너 처리 실패: {error_message or container_status}")

        time.sleep(THREADS_CONTAINER_POLL_INTERVAL_SECONDS)
        waited_seconds += THREADS_CONTAINER_POLL_INTERVAL_SECONDS

    raise RuntimeError(
        "Threads 컨테이너 준비 시간이 초과되었습니다: "
        f"{THREADS_CONTAINER_MAX_WAIT_SECONDS}초"
    )


def publish_threads_media(creation_id: str) -> str:
    load_dotenv()

    threads_access_token = os.getenv("THREADS_ACCESS_TOKEN")
    threads_user_id = os.getenv("THREADS_USER_ID")

    url = f"{THREADS_API_BASE_URL}/{threads_user_id}/threads_publish"

    payload = {
        "creation_id": creation_id,
        "access_token": threads_access_token,
    }

    response = requests.post(url, data=payload, timeout=30)
    data = response.json()

    if response.status_code >= 400 or "id" not in data:
        raise RuntimeError(f"Threads 게시 실패: {data}")

    return data["id"]


def publish_article_to_threads(article: Article) -> Article:
    try:
        creation_id = create_threads_media_container(article)
        wait_for_threads_media_container(creation_id)
        threads_post_id = publish_threads_media(creation_id)

        article.threads_publish_status = STATUS_SUCCESS
        article.threads_post_id = threads_post_id
        article.threads_publish_error = ""

        print(f" -> Threads 게시 완료: {threads_post_id}")

    except Exception as e:
        article.threads_publish_status = STATUS_FAILED
        article.threads_post_id = ""
        article.threads_publish_error = str(e)

        print(f" -> Threads 게시 실패: {e}")

    return article