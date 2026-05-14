import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient


def generate_huggingface_image(article, run_dir):
    load_dotenv()

    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError(".env 파일에 HF_TOKEN을 먼저 입력하세요.")

    if not article.get("sdxl_image_prompt"):
        article["image_path"] = ""
        article["image_generation_status"] = "skipped_no_sdxl_prompt"
        return article

    output_dir = run_dir / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"article_{article['id']}.png"

    client = InferenceClient(token=hf_token)

    image = client.text_to_image(
        prompt=article["sdxl_image_prompt"],
        negative_prompt=(
            "text, watermark, logo, low quality, blurry, distorted face, "
            "extra fingers, oversaturated, artificial glow"
        ),
        model="stabilityai/stable-diffusion-3.5-large",
        width=1024,
        height=1280,
        num_inference_steps=30,
        guidance_scale=7.5,
    )

    image.save(image_path)

    article["image_path"] = str(image_path)
    article["image_generation_status"] = "success"

    return article


def generate_huggingface_images(selected_articles, run_dir):
    for article in selected_articles:
        print(f"Hugging Face 이미지 생성 중: {article['title'][:30]}...")
        generate_huggingface_image(article, run_dir)

    return selected_articles
