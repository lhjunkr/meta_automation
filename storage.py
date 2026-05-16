import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from constants import (
    R2_UPLOAD_STATUS_FAILED,
    R2_UPLOAD_STATUS_SKIPPED_NO_FINAL_IMAGE,
    STATUS_SUCCESS,
)
from models import Article


def create_r2_client():
    load_dotenv()

    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key_id = os.getenv("R2_ACCESS_KEY_ID")
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")

    if not account_id or not access_key_id or not secret_access_key:
        raise RuntimeError(".env에 R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY를 입력하세요.")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


def upload_image_to_r2(local_path, object_key):
    load_dotenv()

    bucket_name = os.getenv("R2_BUCKET_NAME")
    public_base_url = os.getenv("R2_PUBLIC_BASE_URL")

    if not bucket_name or not public_base_url:
        raise RuntimeError(".env에 R2_BUCKET_NAME, R2_PUBLIC_BASE_URL을 입력하세요.")

    local_path = Path(local_path)

    if not local_path.exists():
        raise FileNotFoundError(f"업로드할 이미지 파일을 찾을 수 없습니다: {local_path}")

    client = create_r2_client()

    try:
        # Meta Graph API가 image_url을 다시 가져가므로 공개 URL에서 PNG로 인식되도록 Content-Type을 고정합니다.
        client.upload_file(
            str(local_path),
            bucket_name,
            object_key,
            ExtraArgs={"ContentType": "image/png"},
        )
    except ClientError as e:
        raise RuntimeError(f"R2 업로드 실패: {e}") from e

    return f"{public_base_url.rstrip('/')}/{object_key}"


def upload_article_images_to_r2(selected_articles: list[Article], run_dir) -> list[Article]:
    run_date = run_dir.name

    for article in selected_articles:
        print(f"R2 이미지 업로드 중: {article.title[:30]}...")

        final_image_path = article.final_image_path

        if not final_image_path:
            article.public_image_url = ""
            article.r2_upload_status = R2_UPLOAD_STATUS_SKIPPED_NO_FINAL_IMAGE
            print(" -> 최종 이미지가 없어 R2 업로드를 건너뜁니다.")
            continue

        # 날짜별 prefix를 사용해 Actions artifact와 R2 객체 경로를 같은 실행 단위로 추적합니다.
        object_key = f"{run_date}/article_{article.id}_final.png"

        try:
            public_url = upload_image_to_r2(final_image_path, object_key)
        except Exception as e:
            article.public_image_url = ""
            article.r2_upload_status = R2_UPLOAD_STATUS_FAILED
            print(f" -> R2 업로드 실패: {e}")
            continue

        article.public_image_url = public_url
        article.r2_upload_status = STATUS_SUCCESS
        print(f" -> R2 업로드 완료: {public_url}")

    return selected_articles
