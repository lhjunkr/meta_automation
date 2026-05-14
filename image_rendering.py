import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


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


def wrap_text(draw, text, font, max_width, max_lines=2):
    words = text.split()
    lines = []
    current = ""

    for word in words:
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

    for unwanted_character in ["▯", "□", "☒", "×"]:
        cleaned_title = cleaned_title.replace(unwanted_character, "")

    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()

    if " - " in cleaned_title:
        cleaned_title = cleaned_title.rsplit(" - ", 1)[0]

    return cleaned_title.strip()


def extract_poster_title(article):
    caption = article.get("instagram_caption", "")

    for line in caption.splitlines():
        line = line.strip()
        if line:
            return clean_article_title(line)

    return clean_article_title(article.get("title", ""))


def render_news_image_overlay(article):
    image_path = article.get("image_path")
    if not image_path:
        article["final_image_path"] = ""
        article["image_overlay_status"] = "skipped_no_image"
        return article

    input_path = Path(image_path)
    if not input_path.exists():
        article["final_image_path"] = ""
        article["image_overlay_status"] = "image_file_missing"
        return article

    image = Image.open(input_path)
    image = apply_bottom_gradient(image)
    draw = ImageDraw.Draw(image)

    title_font = load_korean_font(55, bold=True)
    footer_font = load_korean_font(35)

    x = 75
    title_y = 900
    footer_y = 1140
    max_width = image.size[0] - (x * 2)

    title = extract_poster_title(article)
    footer = f"출처: {article.get('source', '')} | {datetime.now().strftime('%Y.%m.%d')}"

    title_lines = wrap_text(draw, title, title_font, max_width=max_width, max_lines=2)
    for idx, line in enumerate(title_lines):
        y = title_y + (idx * 70)

        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)]:
            draw.text((x + dx, y + dy), line, fill="#FFFFFF", font=title_font)

    draw.text((x, footer_y), footer, fill=(221, 221, 221, 215), font=footer_font)

    final_path = input_path.with_name(f"{input_path.stem}_final{input_path.suffix}")
    image.convert("RGB").save(final_path, quality=95)

    article["final_image_path"] = str(final_path)
    article["image_overlay_status"] = "success"
    return article


def render_news_image_overlays(selected_articles):
    for article in selected_articles:
        print(f"이미지 텍스트 합성 중: {article['title'][:30]}...")
        render_news_image_overlay(article)

    return selected_articles
