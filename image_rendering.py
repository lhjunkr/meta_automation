import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from constants import (
    IMAGE_OVERLAY_STATUS_FILE_MISSING,
    IMAGE_OVERLAY_STATUS_SKIPPED_NO_IMAGE,
    STATUS_SUCCESS,
)
from models import Article
from time_utils import now_kst

STORY_IMAGE_SIZE = (1080, 1920)
STORY_BACKGROUND_BLUR_RADIUS = 40
STORY_BACKGROUND_DIM_ALPHA = 90


def load_korean_font(size, bold=False):
    if bold:
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/NanumGothicBold.ttf",
        ]
    else:
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/NanumGothic.ttf",
        ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue

    raise RuntimeError("사용 가능한 한글 폰트를 찾지 못했습니다.")


def apply_bottom_gradient(image):
    image = image.convert("RGBA")
    width, height = image.size
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gradient_pixels = gradient.load()
    if gradient_pixels is None:
        raise RuntimeError("그라데이션 픽셀 버퍼를 초기화하지 못했습니다.")

    start_y = int(height * 0.68)

    for y in range(start_y, height):
        progress = (y - start_y) / max(height - start_y, 1)
        alpha = int(235 * progress)
        for x in range(width):
            gradient_pixels[x, y] = (0, 0, 0, alpha)

    return Image.alpha_composite(image, gradient)


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def split_long_word(draw, word, font, max_width):
    chunks = []
    current = ""

    for character in word:
        candidate = current + character

        if not current or text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue

        chunks.append(current)
        current = character

    if current:
        chunks.append(current)

    return chunks


def wrap_text(draw, text, font, max_width, max_lines=2):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        if text_width(draw, word, font) > max_width:
            if current:
                lines.append(current)
                current = ""

            for word_chunk in split_long_word(draw, word, font, max_width):
                if len(lines) >= max_lines:
                    break
                lines.append(word_chunk)

            if len(lines) >= max_lines:
                break

            continue

        candidate = word if not current else f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines:
        remaining_text = " ".join(words)
        joined = " ".join(lines)
        if len(joined) < len(remaining_text):
            while lines[-1] and text_width(draw, lines[-1] + "...", font) > max_width:
                lines[-1] = lines[-1][:-1].rstrip()
            lines[-1] = lines[-1] + "..."

    return lines


def clean_article_title(title):
    cleaned_title = title

    for breaking_news_prefix in ["[속보]", "【속보】", "(속보)", "속보"]:
        cleaned_title = cleaned_title.replace(breaking_news_prefix, "")

    for unwanted_character in ["🚨", "⚠️", "✅", "📍", "🔎", "💡", "▯", "□", "☒", "×"]:
        cleaned_title = cleaned_title.replace(unwanted_character, "")

    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()

    if " - " in cleaned_title:
        cleaned_title = cleaned_title.rsplit(" - ", 1)[0]

    return cleaned_title.strip()


def extract_poster_title(article: Article) -> str:
    caption = article.instagram_caption

    for line in caption.splitlines():
        line = line.strip()
        if line:
            return clean_article_title(line)

    return clean_article_title(article.title)


def render_news_image_overlay(article: Article) -> Article:
    image_path = article.image_path
    if not image_path:
        article.final_image_path = ""
        article.image_overlay_status = IMAGE_OVERLAY_STATUS_SKIPPED_NO_IMAGE
        return article

    input_path = Path(image_path)
    if not input_path.exists():
        article.final_image_path = ""
        article.image_overlay_status = IMAGE_OVERLAY_STATUS_FILE_MISSING
        return article

    image = Image.open(input_path)
    image = apply_bottom_gradient(image)
    draw = ImageDraw.Draw(image)

    badge_font = load_korean_font(38, bold=True)
    title_font = load_korean_font(55, bold=True)
    footer_font = load_korean_font(35)

    x = 75
    badge_y = 895   # [속보] 위치 설정
    title_y = 940
    title_line_gap = 70
    footer_gap = 22
    max_width = image.size[0] - (x * 2)

    title = extract_poster_title(article)
    footer = f"출처: {article.source} | {now_kst().strftime('%Y.%m.%d')}"

    # 지원되지 않는 이모지가 제목 줄바꿈에 영향을 주지 않도록 속보 라벨은 따로 그립니다.
    draw.text((x, badge_y), "[속보]", fill="#FFFFFF", font=badge_font)

    title_lines = wrap_text(draw, title, title_font, max_width=max_width, max_lines=2)
    for idx, line in enumerate(title_lines):
        y = title_y + (idx * title_line_gap)

        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)]:
            draw.text((x + dx, y + dy), line, fill="#FFFFFF", font=title_font)

    footer_y = title_y + (len(title_lines) * title_line_gap) + footer_gap
    draw.text((x, footer_y), footer, fill=(221, 221, 221, 215), font=footer_font)
    final_path = input_path.with_name(f"{input_path.stem}_final{input_path.suffix}")
    image.convert("RGB").save(final_path, quality=95)

    article.final_image_path = str(final_path)
    article.image_overlay_status = STATUS_SUCCESS
    return article


def render_news_image_overlays(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"이미지 텍스트 합성 중: {article.title[:30]}...")
        render_news_image_overlay(article)

    return selected_articles


def build_story_image(poster_image):
    story_width, story_height = STORY_IMAGE_SIZE
    poster_image = poster_image.convert("RGB")
    poster_width, poster_height = poster_image.size

    # 9:16 화면을 꽉 채우도록 확대한 포스터를 흐리게 깔아 위아래 빈 공간을 메웁니다.
    cover_scale = max(story_width / poster_width, story_height / poster_height)
    cover_size = (round(poster_width * cover_scale), round(poster_height * cover_scale))
    background = poster_image.resize(cover_size, Image.Resampling.LANCZOS)
    crop_left = (cover_size[0] - story_width) // 2
    crop_top = (cover_size[1] - story_height) // 2
    background = background.crop(
        (crop_left, crop_top, crop_left + story_width, crop_top + story_height)
    )
    background = background.filter(ImageFilter.GaussianBlur(STORY_BACKGROUND_BLUR_RADIUS))
    dim_layer = Image.new("RGB", STORY_IMAGE_SIZE, (0, 0, 0))
    background = Image.blend(background, dim_layer, STORY_BACKGROUND_DIM_ALPHA / 255)

    # 제목 오버레이가 잘리지 않도록 원본 포스터는 가로 폭에 맞춰 가운데에 그대로 둡니다.
    fit_scale = story_width / poster_width
    poster_size = (story_width, round(poster_height * fit_scale))
    poster = poster_image.resize(poster_size, Image.Resampling.LANCZOS)
    background.paste(poster, (0, (story_height - poster_size[1]) // 2))

    return background


def render_story_image(article: Article) -> Article:
    final_image_path = article.final_image_path
    if not final_image_path or not Path(final_image_path).exists():
        article.story_image_path = ""
        return article

    final_path = Path(final_image_path)
    story_path = final_path.with_name(f"{final_path.stem.removesuffix('_final')}_story.jpg")

    try:
        with Image.open(final_path) as poster_image:
            story_image = build_story_image(poster_image)
        story_image.save(story_path, format="JPEG", quality=95)
    except Exception as e:
        # 스토리는 보조 산출물이라 실패해도 피드 게시 파이프라인은 그대로 진행합니다.
        article.story_image_path = ""
        print(f" -> 스토리 이미지 생성 실패: {e}")
        return article

    article.story_image_path = str(story_path)
    return article


def render_story_images(selected_articles: list[Article]) -> list[Article]:
    for article in selected_articles:
        print(f"스토리 이미지 생성 중: {article.title[:30]}...")
        render_story_image(article)

    return selected_articles
