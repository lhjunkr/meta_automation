import json
from datetime import datetime
from pathlib import Path


def append_publish_history(selected_articles, status="ready"):
    published_at = datetime.now().isoformat(timespec="seconds")

    with open("history.jsonl", "a", encoding="utf-8") as f:
        for article in selected_articles:
            record = {
                "published_at": published_at,
                "status": status,
                "category": article.get("category", ""),
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "google_link": article.get("google_link", ""),
                "resolved_link": article.get("resolved_link", ""),
                "instagram_post_id": article.get("instagram_post_id", ""),
                "final_image_path": article.get("final_image_path", ""),
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def count_today_published():
    history_path = Path("history.jsonl")

    if not history_path.exists():
        return 0

    today = datetime.now().date()
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

            if record.get("status") != "published":
                continue

            published_at = record.get("published_at", "")

            try:
                published_date = datetime.fromisoformat(published_at).date()
            except ValueError:
                continue

            if published_date == today:
                count += 1

    return count


def is_already_published(article):
    history_path = Path("history.jsonl")

    if not history_path.exists():
        return False

    current_google_link = article.get("google_link", "")
    current_resolved_link = article.get("resolved_link", "")
    current_public_image_url = article.get("public_image_url", "")

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if current_google_link and current_google_link == record.get("google_link"):
                return True

            if current_resolved_link and current_resolved_link == record.get("resolved_link"):
                return True

            if current_public_image_url and current_public_image_url == record.get("public_image_url"):
                return True

    return False
