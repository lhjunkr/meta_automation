import base64
import json
from pathlib import Path

import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder
from pygooglenews import GoogleNews

from constants import (
    ARTICLE_STATUS_DOWNLOAD_FAILED,
    ARTICLE_STATUS_RESOLVE_FAILED,
    STATUS_SUCCESS,
)

from models import Article

# pygooglenews still imports feedparser 5.x, which expects this Python 2-era alias.
# Define it before pygooglenews imports feedparser so GitHub Actions can run on Python 3.11.
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


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


def is_excluded_source(source):
    normalized_source = source.lower()
    return any(keyword.lower() in normalized_source for keyword in EXCLUDED_SOURCE_KEYWORDS)


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


def resolve_selected_article_links(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"URL 정화 중: {article.title[:30]}...")
        article.resolved_link = resolve_article_url(article.google_link)

    return selected_articles


def fetch_article_body(resolved_link: str) -> tuple[str, str]:
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
        return "", ARTICLE_STATUS_DOWNLOAD_FAILED

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
    return body, STATUS_SUCCESS


def fetch_selected_article_bodies(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"본문 수집 중: {article.title[:30]}...")

        if not article.resolved_link:
            article.body = ""
            article.status = ARTICLE_STATUS_RESOLVE_FAILED
            print(" -> 원문 URL이 없어 본문 수집을 건너뜁니다.")
            continue

        article.body, article.status = fetch_article_body(article.resolved_link)

    return selected_articles
