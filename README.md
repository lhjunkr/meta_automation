# Meta Automation

Google News 후보 기사를 수집하고, Gemini로 기사 3개를 선별한 뒤, 한국어 캡션과 뉴스 포스터 이미지를 생성해 Instagram과 Facebook Page에 게시하는 자동화 프로젝트입니다.

운영 환경은 GitHub Actions입니다. 매일 한국 시간 오전 6시 23분에 자동 실행되며, Actions 탭에서 수동 실행도 가능합니다.

![Meta Automation Architecture](docs/architecture.jpeg)

## 현재 운영 설정

| 항목 | 값 |
| --- | --- |
| Workflow | `.github/workflows/daily-upload.yml` |
| 실행 환경 | GitHub-hosted Ubuntu runner |
| 예약 실행 | `23 21 * * *` UTC, KST 06:23 |
| 수동 실행 | `workflow_dispatch` |
| Python | 3.11 |
| 게시 모드 | `DRY_RUN=false` |
| 일일 게시 한도 | `MAX_DAILY_POSTS=3` |
| 게시 윈도우 | `UPLOAD_WINDOW_MINUTES=15` |
| 게시 간격 | `POST_SPACING_MINUTES=5` |
| 리포트 | SMTP 이메일 + GitHub artifact |

## 실행 흐름

1. GitHub Actions가 코드를 checkout합니다.
2. Python, Noto CJK 폰트, 운영 의존성을 설치합니다.
3. 개발 의존성을 설치한 뒤 `ruff`, `mypy`, `unittest`를 실행합니다.
4. GitHub Secrets로 `.env`를 생성합니다.
5. `main.py`가 전체 자동화 파이프라인을 실행합니다.
6. Google News에서 후보 기사를 수집하고 기존 게시 이력과 제외 언론사를 필터링합니다.
7. Gemini가 카테고리별 primary 기사와 backup 기사를 선택합니다.
8. 선택된 기사는 `Article` dataclass로 관리됩니다.
9. URL 정화, 본문 추출, 캡션 생성, 이미지 프롬프트 생성, 이미지 생성, 포스터 렌더링, R2 업로드를 순서대로 수행합니다.
10. primary 기사가 완성 조건을 통과하지 못하면 같은 카테고리의 backup 기사를 다시 처리합니다.
11. 게시 전 Meta preflight로 Instagram 계정과 Facebook Page 접근 권한을 확인합니다.
12. Instagram과 Facebook Page에 게시하고, 성공한 게시 기록을 `history.jsonl`에 저장합니다.
13. 실행 산출물과 실패 요약을 이메일과 GitHub artifact로 남깁니다.
14. 성공 시 GitHub Actions가 `history.jsonl`을 `main` 브랜치에 커밋합니다.

## 주요 모듈

| 파일 | 역할 |
| --- | --- |
| `main.py` | 전체 batch 실행 진입점 |
| `models.py` | `Article` dataclass와 dict 변환 계층 |
| `constants.py` | 상태값 문자열 중앙화 |
| `time_utils.py` | KST 기준 시간 처리 |
| `config.py` | 환경변수 기반 런타임 설정 |
| `news.py` | Google News 수집, URL 정화, 본문 추출 |
| `content.py` | Gemini 기사 선정, 캡션 생성, 이미지 프롬프트 생성 |
| `image_generation.py` | Hugging Face 이미지 생성 및 모델 fallback |
| `image_rendering.py` | 뉴스 포스터 텍스트 합성 |
| `storage.py` | Cloudflare R2 업로드 |
| `pipeline.py` | 콘텐츠 처리, 완성 조건 검사, backup 재시도 |
| `publishing.py` | Meta preflight, Instagram/Facebook 게시 |
| `outputs.py` | 실행 산출물 저장 |
| `reporting.py` | 실패 요약 리포트 생성 |
| `history.py` | 게시 이력 기록과 중복 게시 방지 |
| `tests/` | 핵심 dataclass, pipeline, 렌더링 유닛 테스트 |

## 데이터 모델

기사 데이터는 `models.Article` dataclass로 관리합니다.

주요 필드:

```text
id
category
title
source
google_link
backup_article
resolved_link
body
instagram_caption
sdxl_image_prompt
image_path
final_image_path
public_image_url
publish_status
```

`Article.from_dict()`와 `Article.to_dict()`는 기존 산출물이나 외부 입력과의 호환을 위해 유지합니다. 알 수 없는 필드는 `extra_fields`에 보존되어 스키마 변경 중에도 데이터가 유실되지 않도록 합니다.

## 이미지 생성 전략

이미지 생성은 Hugging Face Inference API를 사용합니다. 외부 provider timeout이나 모델 장애가 전체 실행 실패로 번지지 않도록 모델을 순서대로 시도합니다.

현재 모델 우선순위:

```text
1. stabilityai/stable-diffusion-3.5-large-turbo
2. stabilityai/stable-diffusion-xl-base-1.0
3. black-forest-labs/FLUX.1-schnell
```

모든 모델이 실패하면 해당 기사는 `generation_failed` 상태가 되고, 카테고리 backup 기사 처리로 넘어갑니다.

## 게시 조건

기사는 아래 조건을 모두 만족해야 게시 대상이 됩니다.

- 본문 추출 성공
- Gemini 캡션 생성 성공
- 이미지 프롬프트 생성 성공
- Hugging Face 이미지 생성 성공
- 포스터 렌더링 성공
- R2 업로드 성공
- `final_image_path` 존재
- `public_image_url` 존재

primary 기사가 실패하면 backup 기사를 처리합니다. primary와 backup 모두 실패하면 해당 카테고리는 `failed_categories.txt`에 기록됩니다.

## Meta 게시

게시 전 `publishing.py`의 preflight가 먼저 실행됩니다.

검증 대상:

- `META_ACCESS_TOKEN`으로 `IG_USER_ID` 조회 가능 여부
- `FACEBOOK_PAGE_ACCESS_TOKEN`으로 `FACEBOOK_PAGE_ID` 조회 가능 여부

preflight가 실패하면 Instagram media container나 Facebook photo publish 요청을 보내지 않습니다.

## 산출물

모든 실행 결과는 KST 날짜 기준 폴더에 저장됩니다.

```text
outputs/YYYY-MM-DD/
```

대표 파일:

```text
gemini_selected_result.txt
selected_news.txt
selected_articles.txt
instagram_captions.txt
sdxl_image_prompts.txt
generated_images.txt
failed_categories.txt
failure_report.txt
images/
```

`failure_report.txt`는 이메일 본문에도 포함됩니다. `outputs/**/*.txt`는 이메일 첨부와 GitHub artifact로 함께 보관됩니다.

게시 성공 기록은 아래 파일에 누적됩니다.

```text
history.jsonl
```

이 파일은 중복 게시 방지와 일일 게시 한도 계산에 사용되므로, GitHub Actions가 성공 실행 후 `main` 브랜치에 자동 커밋합니다.

## 필요한 GitHub Secrets

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 아래 값을 등록합니다.

### Gemini / Hugging Face

```text
GEMINI_API_KEY
HF_TOKEN
```

### Cloudflare R2

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_PUBLIC_BASE_URL
```

### Meta / Instagram / Facebook

```text
META_ACCESS_TOKEN
IG_USER_ID
FACEBOOK_PAGE_ID
FACEBOOK_PAGE_ACCESS_TOKEN
```

`META_ACCESS_TOKEN`과 `FACEBOOK_PAGE_ACCESS_TOKEN`은 Meta Business Settings에서 발급한 운영용 System User token을 사용합니다.

### 이메일 리포트

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
REPORT_EMAIL_TO
```

Gmail SMTP 예시:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<sender-gmail-address>
SMTP_PASSWORD=<gmail-app-password>
REPORT_EMAIL_TO=<recipient-email-address>
```

## 로컬 개발

가상환경을 만들고 운영 의존성을 설치합니다.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

정적 검사와 테스트를 실행하려면 개발 의존성도 설치합니다.

```bash
pip install -r requirements-dev.txt
```

로컬 실행용 `.env` 파일을 만듭니다.

```env
GEMINI_API_KEY=
HF_TOKEN=

R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_BASE_URL=

META_ACCESS_TOKEN=
IG_USER_ID=
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=

MAX_DAILY_POSTS=3
UPLOAD_WINDOW_MINUTES=15
POST_SPACING_MINUTES=5
```

주의: 실제 운영 값은 GitHub Actions Secrets를 기준으로 관리합니다. 로컬 `.env`가 운영 Secrets와 다르면 로컬 게시 검증 결과는 신뢰하지 않습니다.

## 검사 명령

문법 검사:

```bash
python3 -m py_compile main.py models.py constants.py reporting.py pipeline.py image_generation.py content.py news.py image_rendering.py storage.py outputs.py publishing.py history.py config.py time_utils.py
```

정적 검사:

```bash
python3 -m ruff check .
python3 -m mypy .
```

유닛 테스트:

```bash
python3 -m unittest discover -s tests
```

전체 로컬 검사:

```bash
python3 -m ruff check .
python3 -m mypy .
python3 -m unittest discover -s tests
```

## 운영 메모

- 노트북이 켜져 있지 않아도 GitHub-hosted runner에서 실행됩니다.
- 예약 실행 기준은 KST 06:23입니다.
- 날짜 폴더, 포스터 날짜, 일일 게시 한도는 KST 기준입니다.
- `DRY_RUN=false`이면 수동 실행도 실제 Instagram/Facebook에 게시합니다.
- 게시 간격은 `UPLOAD_WINDOW_MINUTES`와 `POST_SPACING_MINUTES`로 제어합니다.
- 일부 언론사는 자동 다운로드에 `401`, `403`, `402`를 반환할 수 있습니다.
- `trafilatura`가 본문을 충분히 추출하지 못하면 article-level 실패로 처리하고 backup 기사로 넘어갑니다.
- Meta 오류가 `OAuthException`, `code 190`, `Session has expired` 형태로 나오면 System User token, Page/Instagram asset 권한, GitHub Secrets를 먼저 확인합니다.

## 자주 쓰는 명령

상태 확인:

```bash
git status --short --branch
```

최신 원격 반영:

```bash
git pull --rebase origin main
```

변경 커밋:

```bash
git add <files>
git commit -m "<message>"
git push origin main
```

GitHub Actions 실행 후 `history.jsonl` push 충돌이 나면 원격 이력을 먼저 당겨옵니다.

```bash
git pull --rebase origin main
git push origin main
```

## 보안 원칙

절대 커밋하면 안 되는 파일:

```text
.env
```

이 프로젝트는 공식 API를 사용합니다.

- Google Gemini API
- Hugging Face Inference API
- Cloudflare R2 S3-compatible API
- Meta Graph API
- SMTP

사용자는 각 뉴스 발행사 정책, API 제공자 약관, Meta Platform 정책, 저작권 기준을 준수해야 합니다.
