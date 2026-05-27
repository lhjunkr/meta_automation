import json
import os
from datetime import date, datetime
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
from time_utils import today_kst


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


R2_HISTORY_PREFIX = "private/history"


def get_r2_bucket_name() -> str:
    load_dotenv()

    bucket_name = os.getenv("R2_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError(".env에 R2_BUCKET_NAME을 입력하세요.")

    return bucket_name


def build_r2_history_key(run_date: str) -> str:
    return f"{R2_HISTORY_PREFIX}/{run_date}/history.jsonl"


def parse_r2_history_date(object_key: str) -> date | None:
    prefix = f"{R2_HISTORY_PREFIX}/"

    if not object_key.startswith(prefix) or not object_key.endswith("/history.jsonl"):
        return None

    date_text = object_key.removeprefix(prefix).split("/", 1)[0]

    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_recent_history_key(object_key: str, keep_days: int) -> bool:
    history_date = parse_r2_history_date(object_key)

    if not history_date:
        return False

    age_days = (today_kst() - history_date).days
    return 0 <= age_days < keep_days


def list_r2_history_keys(client, bucket_name: str) -> list[str]:
    history_keys: list[str] = []
    continuation_token = None

    while True:
        list_kwargs = {
            "Bucket": bucket_name,
            "Prefix": f"{R2_HISTORY_PREFIX}/",
        }

        if continuation_token:
            list_kwargs["ContinuationToken"] = continuation_token

        response = client.list_objects_v2(**list_kwargs)

        for item in response.get("Contents", []):
            object_key = item.get("Key", "")

            if object_key:
                history_keys.append(object_key)

        if not response.get("IsTruncated"):
            break

        continuation_token = response.get("NextContinuationToken")

    return history_keys


def download_recent_publish_history_from_r2(
    local_history_path: str = "history.jsonl",
    keep_days: int = 3,
) -> None:
    client = create_r2_client()
    bucket_name = get_r2_bucket_name()
    history_keys = [
        object_key
        for object_key in list_r2_history_keys(client, bucket_name)
        if is_recent_history_key(object_key, keep_days)
    ]

    if not history_keys:
        print("R2 게시 이력 없음: 새 history.jsonl로 시작합니다.")
        Path(local_history_path).write_text("", encoding="utf-8")
        return

    history_lines = []
    seen_lines = set()

    for object_key in sorted(history_keys):
        response = client.get_object(Bucket=bucket_name, Key=object_key)
        body = response["Body"].read().decode("utf-8")

        for line in body.splitlines():
            line = line.strip()

            if not line or line in seen_lines:
                continue

            try:
                json.loads(line)
            except json.JSONDecodeError:
                continue

            seen_lines.add(line)
            history_lines.append(line)

    Path(local_history_path).write_text("\n".join(history_lines) + "\n", encoding="utf-8")
    print(f"R2 게시 이력 동기화 완료: {len(history_lines)}건")


def upload_today_publish_history_to_r2(
    run_date: str,
    local_history_path: str = "history.jsonl",
) -> None:
    history_path = Path(local_history_path)

    if not history_path.exists():
        print("업로드할 게시 이력 파일이 없습니다.")
        return

    today_lines = []

    with open(history_path, encoding="utf-8") as history_file:
        for line in history_file:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            published_at = record.get("published_at", "")

            try:
                published_date = datetime.fromisoformat(published_at).date()
            except ValueError:
                continue

            if published_date.isoformat() == run_date:
                today_lines.append(line)

    if not today_lines:
        print("오늘 업로드할 게시 이력이 없습니다.")
        return

    client = create_r2_client()
    bucket_name = get_r2_bucket_name()
    object_key = build_r2_history_key(run_date)
    body = "\n".join(today_lines) + "\n"

    client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=body.encode("utf-8"),
        ContentType="application/jsonl; charset=utf-8",
    )
    print(f"R2 게시 이력 업로드 완료: {object_key}")


def cleanup_old_r2_publish_history(keep_days: int = 3) -> None:
    client = create_r2_client()
    bucket_name = get_r2_bucket_name()

    for object_key in list_r2_history_keys(client, bucket_name):
        history_date = parse_r2_history_date(object_key)

        if not history_date:
            continue

        age_days = (today_kst() - history_date).days

        if age_days >= keep_days:
            client.delete_object(Bucket=bucket_name, Key=object_key)
            print(f"오래된 R2 게시 이력 삭제: {object_key}")


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
