# ruff: noqa: I001
import base64
import json
from pathlib import Path

import requests
import trafilatura
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder
from readability import Document

# pygooglenews가 불러오는 feedparser 5.x는 Python 3.11에서 사라진
# base64.decodestring을 참조하므로, pygooglenews import 전에 호환 별칭을 만듭니다.
if not hasattr(base64, "decodestring"):
    base64.decodestring = base64.decodebytes

from pygooglenews import GoogleNews

from constants import (
    ARTICLE_STATUS_DOWNLOAD_FAILED,
    ARTICLE_STATUS_RESOLVE_FAILED,
    STATUS_SUCCESS,
)
from models import Article


MIN_ARTICLE_BODY_LENGTH = 300

# 일부 언론사는 기본 Python 요청을 차단하므로 브라우저에 가까운 헤더로 본문 수집 성공률을 높입니다.
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
    seen_links: set[str] = set()
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
    raw_news: list[dict] = []

    def add_news(entries, category_name):
        added_count = 0

        for entry in entries:
            # 같은 Google News 링크가 여러 섹션에 중복 노출될 수 있어 수집 단계에서 먼저 제거합니다.
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
        # Google News RSS 링크는 중계 URL이므로 원문 URL로 정화한 뒤 본문 수집에 사용합니다.
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


def extract_body_with_trafilatura(html: str, url: str) -> str:
    body = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
    )

    return body or ""


def extract_body_with_readability(html: str) -> str:
    document = Document(html)
    summary_html = document.summary()

    soup = BeautifulSoup(summary_html, "html.parser")
    return soup.get_text("\n", strip=True)


def extract_body_with_beautifulsoup(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    text_blocks = []

    for tag in soup.find_all(["article", "main", "section", "p"]):
        text = tag.get_text(" ", strip=True)

        if len(text) >= 40:
            text_blocks.append(text)

    return "\n".join(text_blocks)


def extract_article_body(html: str, url: str) -> tuple[str, str]:
    extractors = [
        ("trafilatura", lambda: extract_body_with_trafilatura(html, url)),
        ("readability", lambda: extract_body_with_readability(html)),
        ("beautifulsoup", lambda: extract_body_with_beautifulsoup(html)),
    ]

    last_error = ""

    for extractor_name, extractor in extractors:
        try:
            body = extractor()
        except Exception as e:
            last_error = str(e)
            print(f"본문 추출기 실패: {extractor_name} ({e})")
            continue

        body = body.strip()

        if len(body) >= MIN_ARTICLE_BODY_LENGTH:
            print(f" -> 본문 추출 완료({extractor_name}): {len(body)}자")
            return body, STATUS_SUCCESS

        print(f" -> 본문이 너무 짧음({extractor_name}): {len(body)}자")

    return "", f"extract_failed:{last_error}" if last_error else "extract_failed"


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

    return extract_article_body(response.text, resolved_link)


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