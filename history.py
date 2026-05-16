import json
from datetime import datetime
from pathlib import Path

from constants import STATUS_PUBLISHED, STATUS_READY
from models import Article
from time_utils import now_kst, today_kst


def append_publish_history(selected_articles: list[Article], status: str = STATUS_READY) -> None:
    # GitHub Actions runner의 기본 시간대와 무관하게 게시 이력은 운영 기준인 KST로 남깁니다.
    published_at = now_kst().isoformat(timespec="seconds")

    with open("history.jsonl", "a", encoding="utf-8") as f:
        for article in selected_articles:
            record = {
                "published_at": published_at,
                "status": status,
                "category": article.category,
                "title": article.title,
                "source": article.source,
                "google_link": article.google_link,
                "resolved_link": article.resolved_link,
                "instagram_post_id": article.instagram_post_id,
                "final_image_path": article.final_image_path,
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

def count_today_published() -> int:
    history_path = Path("history.jsonl")

    if not history_path.exists():
        return 0

    # 일일 게시 한도는 한국 계정 운영 시간 기준으로 계산합니다.
    today = today_kst()
    count = 0

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("status") != STATUS_PUBLISHED:
                continue

            published_at = record.get("published_at", "")

            try:
                published_date = datetime.fromisoformat(published_at).date()
            except ValueError:
                continue

            if published_date == today:
                count += 1

    return count

def is_already_published(article: Article) -> bool:
    history_path = Path("history.jsonl")

    if not history_path.exists():
        return False

    current_google_link = article.google_link
    current_resolved_link = article.resolved_link
    current_public_image_url = article.public_image_url

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Google 링크, 원문 링크, 공개 이미지 URL 중 하나라도 같으면 중복 게시로 간주합니다.
            if current_google_link and current_google_link == record.get("google_link"):
                return True

            if current_resolved_link and current_resolved_link == record.get("resolved_link"):
                return True

            if current_public_image_url and current_public_image_url == record.get("public_image_url"):
                return True

    return False
