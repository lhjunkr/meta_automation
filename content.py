import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


def build_news_context(news_list):
    lines = []

    for news in news_list:
        lines.append(
            "\n".join(
                [
                    f"ID: {news['id']}",
                    f"Category: {news['category']}",
                    f"Title: {news['title']}",
                    f"Source: {news['source']}",
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

    prompt = f"""**Role:** Senior Strategic News Analyst & Professional News Curator.

**Objective:** From the provided list of 30 news articles, select the most valuable articles for a Korean Instagram news account. Your goal is to identify stories that are timely, important, and likely to matter to Korean readers and business decision-makers.

**Important Context:**
- The final Instagram post will be written in Korean.
- Prefer articles that can be clearly explained to a general Korean audience.
- Avoid articles that are too niche, too speculative, or unlikely to produce a useful Korean summary.
- Avoid duplicate stories or articles that cover nearly the same event.

**Strict Selection Criteria (Priority-based):**

1. [종합(KR)]
Choose the article with the highest national importance or public urgency in Korea.
Prioritize:
- major government, legal, diplomatic, safety, public health, or social issues
- breaking events that affect many people
- stories with clear facts and broad public relevance

Avoid:
- minor political remarks
- celebrity/entertainment news
- highly sensational stories with little strategic value

2. [경제(KR)]
Choose the article that signals a meaningful shift in the Korean economy or market.
Prioritize:
- interest rates, inflation, exchange rates, real estate, household debt
- major policy changes affecting businesses or consumers
- important moves by Samsung, SK, Hyundai, LG, Naver, Kakao, or other top-tier Korean companies
- supply chain, semiconductor, AI, energy, or export-related developments

Avoid:
- small company announcements
- promotional business articles
- narrow stock-price-only stories without broader implications

3. [경제(US)]
Choose the article with the strongest global or Korean market implications.
Prioritize:
- Federal Reserve, inflation, employment, Treasury yields, dollar, oil, or trade policy
- AI, Big Tech, chips, cloud, cybersecurity, or global supply chain shifts
- events likely to affect Korean markets, exporters, investors, or strategic planning

Avoid:
- local US-only stories
- opinion pieces without clear facts
- articles blocked behind paywalls when a similar accessible story exists

**Backup Selection Rules:**
- Select exactly two article IDs for each category.
- The first ID is the primary choice.
- The second ID is the backup choice if the primary article fails during processing.
- The backup must be a genuinely different story, not a duplicate of the primary.
- Prefer backup articles with accessible source pages and clear factual content.
- If one article has a stronger headline but likely weak article body access, choose a more accessible article as backup.

**Quality Rules:**
- Do not invent or infer facts beyond the provided list.
- Do not choose an article only because the headline is sensational.
- Prefer articles that can support a clear, concise Korean Instagram caption.
- Do not return title, source, link, summary, explanation, or commentary.
- Return only the machine-parsable output format below.

**Output Format (Strictly for machine parsing):**
Category: 종합(KR)
Primary ID: [Article ID]
Backup ID: [Article ID]

Category: 경제(KR)
Primary ID: [Article ID]
Backup ID: [Article ID]

Category: 경제(US)
Primary ID: [Article ID]
Backup ID: [Article ID]

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


def parse_selected_ids(selected_result):
    selected_items = []
    current_item = {}

    for line in selected_result.splitlines():
        line = line.strip()

        if line.startswith("Category:"):
            if current_item:
                selected_items.append(current_item)
                current_item = {}
            current_item["category"] = line.replace("Category:", "").strip()

        elif line.startswith("Primary ID:"):
            primary_id_text = line.replace("Primary ID:", "").strip()
            current_item["primary_id"] = int(primary_id_text)

        elif line.startswith("Backup ID:"):
            backup_id_text = line.replace("Backup ID:", "").strip()
            current_item["backup_id"] = int(backup_id_text)

    if current_item:
        selected_items.append(current_item)

    return selected_items


def match_selected_articles(selected_result, news_list):
    selected_items = parse_selected_ids(selected_result)
    news_by_id = {news["id"]: news for news in news_list}

    selected_articles = []

    for item in selected_items:
        category = item["category"]

        primary_article = news_by_id.get(item.get("primary_id"))
        backup_article = news_by_id.get(item.get("backup_id"))

        if primary_article:
            primary_article = primary_article.copy()
            primary_article["selection_rank"] = "primary"
            primary_article["backup_article"] = backup_article.copy() if backup_article else None
            selected_articles.append(primary_article)
        else:
            print(f"1순위 ID를 찾을 수 없습니다: {item.get('primary_id')}")

            if backup_article:
                backup_article = backup_article.copy()
                backup_article["selection_rank"] = "backup"
                backup_article["backup_article"] = None
                selected_articles.append(backup_article)
            else:
                print(f"2순위 ID도 찾을 수 없습니다: {category}")

    return selected_articles
