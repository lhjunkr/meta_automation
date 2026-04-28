import os
import trafilatura
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pygooglenews import GoogleNews


def fetch_top_news():
    print("[Step 1] 글로벌 구글 뉴스 데이터 수집 (단일 바구니 필터링 적용)...")

    # 과거 이력 및 중복 확인
    seen_links = set()

    # 과거 이력
    if os.path.exists("history.txt"):
        with open("history.txt", "r", encoding="utf-8") as f:
            seen_links.update(line.strip() for line in f.readlines())
        print(f"어제 기록된 뉴스 {len(seen_links)}건을 블랙리스트에 선탑재했습니다.")
    else:
        print("어제 기록이 없습니다.")

    gn_kr = GoogleNews(lang="ko", country="KR")
    gn_us = GoogleNews(lang="en", country="US")

    raw_news = []

    def add_news(entries, category_name):
        added_count = 0
        for entry in entries:
            if entry.link in seen_links:
                continue

            raw_news.append(
                {"title": entry.title, "link": entry.link, "category": category_name}
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


def build_news_context(news_list):
    lines = []

    for idx, news in enumerate(news_list, start=1):
        lines.append(
            "\n".join(
                [
                    f"No: {idx}",
                    f"Category: {news['category']}",
                    f"Title: {news['title']}",
                    f"Link: {news['link']}",
                ]
            )
        )

    return "\n\n".join(lines)


def select_best_articles(news_list):
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에 GEMINI_API_KEY를 먼저 입력하세요.")

    news_context = build_news_context(news_list)

    prompt = f"""**Role:** Senior Strategic News Analyst & Professional Curator.

**Objective:** From the provided list of 30 news articles, identify and select the single most impactful "Best" article from each category. Your goal is to provide high-value intelligence that a COO would find indispensable.

**Strict Selection Criteria (Priority-based):**
1. [종합(KR)]: Choose the article with the highest social urgency or national importance. Prioritize breaking news that affects the general public.
2. [경제(KR)]: Choose the article that signals a major shift in the Korean market. Prioritize macro-economic data (interest rates, inflation) or game-changing moves by top-tier conglomerates (Samsung, SK, Hyundai, etc.).
3. [경제(US)]: Choose the article with global repercussions. Prioritize Federal Reserve policy shifts, AI/Big Tech disruptions, or critical changes in the global supply chain.

**Selection Logic:**
- If multiple articles meet the criteria, select the one that is most "actionable" or "insightful" for business strategy.
- Do NOT provide any summary or commentary.

**Output Format (Strictly for machine parsing):**
Category: [Category Name]
Title: [Original Title]
Link: [Original Link]

Category: [Category Name]
Title: [Original Title]
Link: [Original Link]

Category: [Category Name]
Title: [Original Title]
Link: [Original Link]

---
**News List to Analyze:**
{news_context}"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )

    return response.text.strip()


def parse_selected_articles(selected_result):
    articles = []
    current_article = {}

    for line in selected_result.splitlines():
        line = line.strip()

        if line.startswith("Category:"):
            if current_article:
                articles.append(current_article)
                current_article = {}
            current_article["category"] = line.replace("Category:", "").strip()
        elif line.startswith("Title:"):
            current_article["title"] = line.replace("Title:", "").strip()
        elif line.startswith("Link:"):
            current_article["link"] = line.replace("Link:", "").strip()

    if current_article:
        articles.append(current_article)

    return articles


def fetch_article_body(url):
    downloaded = trafilatura.fetch_url(url)

    if not downloaded:
        return ""

    body = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
    )

    return body or ""


def fetch_selected_article_bodies(selected_result):
    articles = parse_selected_articles(selected_result)

    for article in articles:
        print(f"본문 수집 중: {article['title'][:30]}...")
        article["body"] = fetch_article_body(article["link"])

    return articles


# --- 테스트 실행 블록 ---
if __name__ == "__main__":
    # 1단계: 뉴스 수집 및 이중 필터링 실행
    news_list = fetch_top_news()

    # 데이터 결과 보고
    print(f"\n필터링 완료. 총 {len(news_list)}개의 신선한 뉴스를 확보했습니다.\n")

    if len(news_list) > 0:
        # 2단계: Gemini가 COO 관점으로 카테고리별 Best 기사 선정
        print("--- [Gemini 선정 결과] ---")
        selected_result = select_best_articles(news_list)
        print(selected_result)

        with open("selected_news.txt", "w", encoding="utf-8") as f:
            f.write(selected_result)

        # 3단계: 선정된 3개 기사 본문 수집
        selected_articles = fetch_selected_article_bodies(selected_result)

        with open("selected_articles.txt", "w", encoding="utf-8") as f:
            for article in selected_articles:
                f.write(f"Category: {article['category']}\n")
                f.write(f"Title: {article['title']}\n")
                f.write(f"Link: {article['link']}\n")
                f.write("Body:\n")
                f.write(article["body"])
                f.write("\n\n---\n\n")

        # history.txt 생성
        with open("history.txt", "w", encoding="utf-8") as f:
            f.write(news_list[0]["link"] + "\n")

        print(
            f"\n[테스트 알림] '{news_list[0]['title'][:20]}...' 기사를 history.txt에 기록했습니다."
        )
        print("한 번 더 실행하면 위 기사가 블랙리스트에 의해 걸러지는지 확인하세요!")
    else:
        print("수집된 뉴스가 없습니다. 구글 뉴스 연결 상태를 확인하세요.")
