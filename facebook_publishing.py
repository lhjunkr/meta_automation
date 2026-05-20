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