import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from huggingface_hub import InferenceClient

from constants import (
    CAPTION_STATUS_SKIPPED_NO_BODY,
    IMAGE_PROMPT_STATUS_SKIPPED_NO_CAPTION,
    STATUS_FAILED,
    STATUS_SUCCESS,
)
from models import Article

GEMINI_TEXT_MODEL = "gemini-2.5-flash-lite"
HF_TEXT_MODEL = "Qwen/Qwen2.5-72B-Instruct"
MAX_IMAGE_PROMPT_BODY_CHARS = 3000
IMAGE_PROMPT_RESPONSE_MARKER = "===IMAGE_PROMPT==="
MIN_IMAGE_PROMPT_LENGTH = 40


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

    # downstream parser가 ID만 읽도록 출력 형식을 고정해 Gemini 응답 흔들림을 줄입니다.
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
        model=GEMINI_TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )

    return (response.text or "").strip()


def parse_selected_ids(selected_result):
    selected_items: list[dict] = []
    current_item: dict = {}

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


def match_selected_articles(selected_result: str, news_list: list[dict]) -> list[Article]:
    selected_items = parse_selected_ids(selected_result)
    news_by_id = {news["id"]: news for news in news_list}

    selected_articles = []

    for item in selected_items:
        category = item["category"]

        primary_article_data = news_by_id.get(item.get("primary_id"))
        backup_article_data = news_by_id.get(item.get("backup_id"))

        if primary_article_data:
            # backup_article을 Article 안에 같이 보관해 primary 실패 시 같은 카테고리 안에서만 재시도합니다.
            primary_article_data = primary_article_data.copy()
            primary_article_data["selection_rank"] = "primary"
            primary_article_data["backup_article"] = (
                backup_article_data.copy() if backup_article_data else None
            )
            selected_articles.append(Article.from_dict(primary_article_data))
        else:
            print(f"1순위 ID를 찾을 수 없습니다: {item.get('primary_id')}")

            if backup_article_data:
                backup_article_data = backup_article_data.copy()
                backup_article_data["selection_rank"] = "backup"
                backup_article_data["backup_article"] = None
                selected_articles.append(Article.from_dict(backup_article_data))
            else:
                print(f"2순위 ID도 찾을 수 없습니다: {category}")

    return selected_articles


# Step 7-1. 기사 본문을 인스타 캡션으로 바꾸기 위한 프롬프트를 만듭니다.
def build_instagram_caption_prompt(article: Article) -> str:
    return f"""**Role:** Professional Korean Social Media News Editor.

You are an Instagram news editor who explains complex news in Korean for readers who may be seeing the issue for the first time.
Your priorities are factual accuracy, clear context, polite Korean tone, and mobile readability.

**Task:**
Write an Instagram post caption in Korean based only on the selected article content provided below.

The caption should be understandable even if the reader has not read any previous article about this issue.

**Critical Constraints:**
1. Write the final output in Korean.
2. Assume the reader is seeing this issue for the first time.
3. Explain the background before explaining the event.
4. Do not just repeat the headline. Explain what changed, who is affected, and why it matters.
5. If you use a technical, financial, legal, diplomatic, or policy term, explain it in plain Korean immediately.
6. Do not invent numbers, dates, names, causes, forecasts, or market effects that are not in the article.
7. Do not use casual speech, slang, exaggerated expressions, fear marketing, or clickbait.
8. Keep the tone calm, factual, and easy to understand.
9. Use short paragraphs with clear line breaks for mobile readability.
10. Keep the entire caption under 700 Korean characters.
11. Do not use Markdown bold syntax such as **text**.
12. Do not include broken symbols, checkbox-like characters, or decorative marks.
13. Do not use prefixes such as [속보], 속보], 속보, or breaking news labels.
14. Every sentence must add context or explanation. Avoid vague filler sentences.

**Output Format:**
===KOREAN_CAPTION===
🚨 [One-line Korean summary written in plain language]

📌 배경
[Explain the context needed to understand this issue in 1-2 short sentences.]

📍 무슨 일이 있었나
[Explain the actual event or change in 1-2 short sentences.]

🔎 왜 중요한가
[Explain who is affected and why this matters in 1-2 short sentences.]

💡 한 줄 정리
[One clear takeaway that a first-time reader can understand.]

[5 topic-specific Korean hashtags]

**Hashtag Rules:**
- Generate exactly 5 Korean hashtags.
- The first hashtag must be #뉴스요약.
- The other 4 hashtags must match the specific article topic.
- Do not use vague hashtags such as #이슈, #정보공유, #소식.
- Do not use unrelated broad hashtags just because they are popular.
- Prefer concrete topic hashtags based on the article title, category, source, and body.
- Use short Korean hashtags without spaces.
- If the article is about markets, rates, housing, chips, AI, energy, trade, policy, diplomacy, safety, or companies, reflect that topic directly.
- Do not invent names or topics that are not in the article.

Examples:
- Real estate article: #뉴스요약 #부동산 #전세 #아파트 #주택시장
- Semiconductor article: #뉴스요약 #반도체 #AI반도체 #수출 #공급망
- Exchange rate article: #뉴스요약 #환율 #달러 #금리 #금융시장
- Diplomacy article: #뉴스요약 #외교 #안보 #국제정세 #정부정책
- Energy article: #뉴스요약 #에너지 #유가 #전력 #산업정책

**Selected Article Content:**
- Title: {article.title}
- Category: {article.category}
- Source: {article.source}
- Body: {article.body}"""


# Step 7-1a. 모델 응답에서 실제 캡션 영역만 분리합니다.
def parse_instagram_caption(raw_text):
    marker = "===KOREAN_CAPTION==="

    if marker in raw_text:
        return raw_text.split(marker, 1)[1].strip()

    return raw_text.strip()


def generate_instagram_caption_with_gemini(article: Article) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에 GEMINI_API_KEY를 먼저 입력하세요.")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_TEXT_MODEL,
        contents=build_instagram_caption_prompt(article),
        config=types.GenerateContentConfig(temperature=0.7),
    )

    return (response.text or "").strip()


def generate_instagram_caption_with_qwen(article: Article) -> str:
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError(".env 파일에 HF_TOKEN을 먼저 입력하세요.")

    client = InferenceClient(token=hf_token)

    response = client.chat_completion(
        model=HF_TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional Korean social media news editor. "
                    "Follow the requested output format exactly. Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": build_instagram_caption_prompt(article),
            },
        ],
        temperature=0.7,
        max_tokens=700,
    )

    return response.choices[0].message.content or ""


# Step 7-2. 기사 1개에 대해 한국어 인스타 캡션을 생성합니다.
def generate_instagram_caption(article: Article) -> Article:
    load_dotenv()

    if article.status != STATUS_SUCCESS or not article.body:
        # 본문이 불완전하면 모델이 제목만 보고 사실을 보태는 위험이 있어 캡션 생성을 건너뜁니다.
        article.instagram_caption_raw = ""
        article.instagram_caption = ""
        article.instagram_caption_status = CAPTION_STATUS_SKIPPED_NO_BODY
        article.instagram_caption_model = ""
        return article

    try:
        raw_text = generate_instagram_caption_with_gemini(article)
        caption_model = GEMINI_TEXT_MODEL
    except Exception as gemini_error:
        print(f" -> Gemini 캡션 생성 실패, Qwen fallback 시도: {gemini_error}")

        try:
            raw_text = generate_instagram_caption_with_qwen(article)
            caption_model = HF_TEXT_MODEL
        except Exception as qwen_error:
            article.instagram_caption_raw = ""
            article.instagram_caption = ""
            article.instagram_caption_status = STATUS_FAILED
            article.instagram_caption_model = ""
            print(f" -> Qwen 캡션 생성 실패: {qwen_error}")
            return article

    article.instagram_caption_raw = raw_text
    article.instagram_caption = parse_instagram_caption(raw_text)
    article.instagram_caption_status = STATUS_SUCCESS
    article.instagram_caption_model = caption_model

    return article


# Step 7-3. 선택된 기사 전체에 대해 인스타 캡션을 순차 생성합니다.
def generate_instagram_captions(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"인스타 캡션 생성 중: {article.title[:30]}...")
        generate_instagram_caption(article)

    return selected_articles


# Step 8-1. 기사 정보와 인스타 캡션을 기반으로 SDXL 이미지 생성 프롬프트를 만듭니다.
def build_sdxl_image_prompt(article: Article) -> str:
    article_body_excerpt = article.body[:MAX_IMAGE_PROMPT_BODY_CHARS]

    return f"""[Persona]
You are a Visual Director specializing in photojournalism. You transform text-based news summaries into highly optimized keyword-based prompts for Stable Diffusion XL (SDXL).

[Input Data]
- Article Title: {article.title}
- Category: {article.category}
- Generated Caption: {article.instagram_caption}
- Article Body Excerpt (maximum {MAX_IMAGE_PROMPT_BODY_CHARS} characters): {article_body_excerpt}

[Task: SDXL Image Prompt (ENGLISH ONLY, KEYWORD FORMAT)]
Create a realistic editorial news photo prompt from the article information above. Output only comma-separated English keywords.

Scene Grounding:
- Before writing the prompt, silently identify one primary subject, one visible action or event, and the most specific supported location or setting.
- Base these three elements directly on the article title, caption, or body excerpt. Do not invent a city, institution, person, object, or event that the article does not support.
- Start the final keyword list with the primary subject, visible action or event, and location or setting, in that order.
- Depict one coherent real-world scene where the subject is visibly connected to the action. Do not combine several unrelated scenes or symbolic concepts.
- If the article describes an abstract topic such as policy, investment, inflation, or diplomacy, represent the concrete people, objects, facilities, documents, products, or public setting explicitly mentioned in the article.
- If no specific location is supported, use a factual setting implied by the subject instead of guessing a city or landmark.

Rules:
- Infer the article's geographic and cultural context from all provided article information: country, city, region, institutions, language, people, policy topic, company, market, or event location.
- Match the visual scene to that context naturally.
- For Korean news, use Korean people when people are needed, Korean urban or institutional settings, Seoul or Korean city atmosphere, Korean offices, Korean streets, Korean public buildings, Korean newsrooms, Korean documents or screens without readable text.
- For non-Korean news, match the relevant country or region: local-looking people, architecture, streets, offices, public buildings, vehicles, clothing, and environmental details appropriate to the article location.
- For global or multinational news, preserve the article's concrete subject and action. Use a neutral international setting only when the article does not support a more specific location.
- Do not force people into the image if the article is better represented by documents, screens, buildings, products, markets, vehicles, or city scenes.
- Do not substitute a generic office, meeting room, newsroom, stock chart, laptop, or city skyline for the article's actual subject unless that element is directly relevant.
- Prefer credible real-world scenes grounded in the article's concrete details.
- Style: photojournalism, documentary editorial photography, candid real-world scene, 35mm lens, natural light, realistic colors, subtle film grain, authentic news photo texture.
- Layout: vertical portrait, main subject in upper half, dark negative space at bottom, soft black gradient at bottom edge, vignette.
- Avoid: glossy advertisement style, cinematic lighting, surrealism, futuristic visuals, exaggerated drama, over-saturation, artificial glow, obvious AI-generated poster look.
- People: no identifiable real people; if included, make them candid, distant, natural, non-identifiable; avoid close-up faces and distorted anatomy.
- Avoid stereotypes, costumes, flags, or symbolic clichés unless directly relevant to the article.
- Always include: no text, no watermark, no logo, no AI art look, no glossy advertisement, no cinematic lighting, no surrealism, no oversaturation, no artificial glow, no distorted anatomy.

[Output Format]
{IMAGE_PROMPT_RESPONSE_MARKER}
(Comma-separated English keywords only)
"""


# Step 8-1a. Gemini 응답에서 실제 이미지 프롬프트만 분리합니다.
def parse_sdxl_image_prompt(raw_text: str) -> str:
    if IMAGE_PROMPT_RESPONSE_MARKER in raw_text:
        return raw_text.split(IMAGE_PROMPT_RESPONSE_MARKER, 1)[1].strip()

    return raw_text.strip()


def validate_sdxl_image_prompt_response(raw_text: str) -> str:
    if not raw_text:
        raise ValueError("Gemini 이미지 프롬프트 응답이 비어 있습니다.")

    if IMAGE_PROMPT_RESPONSE_MARKER not in raw_text:
        raise ValueError("Gemini 이미지 프롬프트 응답에 필수 마커가 없습니다.")

    image_prompt = parse_sdxl_image_prompt(raw_text)

    if len(image_prompt) < MIN_IMAGE_PROMPT_LENGTH:
        raise ValueError(
            "Gemini 이미지 프롬프트가 지나치게 짧습니다: "
            f"{len(image_prompt)}자"
        )

    if "," not in image_prompt:
        raise ValueError("Gemini 이미지 프롬프트가 쉼표 구분 형식이 아닙니다.")

    return image_prompt


# Step 8-2. 기사 1개에 대해 SDXL 이미지 프롬프트를 생성합니다.
def generate_sdxl_image_prompt(article: Article) -> Article:
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(".env 파일에 GEMINI_API_KEY를 먼저 입력하세요.")

    if not article.instagram_caption:
        # 이미지 프롬프트는 최종 캡션 기준으로 만들기 때문에 캡션 없는 기사는 여기서 중단합니다.
        article.sdxl_image_prompt_raw = ""
        article.sdxl_image_prompt = ""
        article.sdxl_image_prompt_status = IMAGE_PROMPT_STATUS_SKIPPED_NO_CAPTION
        return article

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=build_sdxl_image_prompt(article),
        config=types.GenerateContentConfig(temperature=0.7),
    )

    raw_text = (response.text or "").strip()

    article.sdxl_image_prompt_raw = raw_text

    try:
        article.sdxl_image_prompt = validate_sdxl_image_prompt_response(raw_text)
    except ValueError as validation_error:
        article.sdxl_image_prompt = ""
        article.sdxl_image_prompt_status = STATUS_FAILED
        print(f" -> 이미지 프롬프트 응답 검증 실패: {validation_error}")
        return article

    article.sdxl_image_prompt_status = STATUS_SUCCESS

    return article


# Step 8-3. 선택된 기사 전체에 대해 이미지 프롬프트를 순차 생성합니다.
def generate_sdxl_image_prompts(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"SDXL 이미지 프롬프트 생성 중: {article.title[:30]}...")
        generate_sdxl_image_prompt(article)

    return selected_articles
