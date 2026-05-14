# Meta Automation

Google News articles are collected, curated with Gemini, transformed into Korean Instagram/Facebook content, rendered as social poster images, uploaded to Cloudflare R2, and published through the Meta Graph API.

The production runner is GitHub Actions. It runs automatically every morning and can also be triggered manually from the Actions tab.

![Meta Automation Architecture](docs/architecture.jpeg)

## Current Operation

| Item | Value |
| --- | --- |
| Workflow | `.github/workflows/daily-upload.yml` |
| Runner | GitHub-hosted Ubuntu runner |
| Schedule | `23 21 * * *` UTC, KST 06:23 |
| Manual trigger | `workflow_dispatch` |
| Python | 3.11 |
| Publishing mode | `DRY_RUN=false` |
| Daily post limit | `MAX_DAILY_POSTS=3` |
| Upload window | `UPLOAD_WINDOW_MINUTES=15` |
| Post spacing | `POST_SPACING_MINUTES=5` |
| Report channel | Email via SMTP |

## Pipeline

| Stage | Responsibility | Main Tools |
| --- | --- | --- |
| News ingestion | Collect Google News candidates and remove already-seen links | `pygooglenews`, `history.jsonl` |
| Filtering | Remove excluded sources and duplicate candidates | Source keyword filters |
| Article selection | Pick primary and backup article IDs per category | Gemini |
| URL resolution | Decode Google News RSS URLs to original publisher URLs | `googlenewsdecoder` |
| Body extraction | Download article pages and extract readable text | `requests`, `trafilatura` |
| Caption generation | Generate Korean Instagram/Facebook post text | Gemini |
| Image prompt generation | Convert caption context into an SDXL prompt | Gemini |
| Image generation | Generate vertical editorial images | Hugging Face Inference API, SDXL |
| Poster rendering | Add gradient, Korean title, source, and date | Pillow, Noto CJK |
| Image hosting | Upload final poster image and create public URL | Cloudflare R2, `boto3` |
| Publishing | Publish to Instagram and Facebook | Meta Graph API |
| History | Record successful posts and prevent duplicates | `history.jsonl` |
| Reporting | Send success/failure run summary | SMTP |

## Architecture Notes

The system is intentionally built as a single scheduled batch pipeline:

1. GitHub Actions prepares Python, fonts, dependencies, and `.env` values from GitHub Secrets.
2. `main.py` collects and filters candidate news.
3. Gemini selects one primary and one backup article for each category.
4. Each selected article goes through URL resolution, body extraction, caption generation, image prompt generation, image generation, poster rendering, and R2 upload.
5. If a primary article fails content checks, the backup article for the same category is processed.
6. Only articles with a valid `public_image_url` are eligible for publishing.
7. Published articles are appended to `history.jsonl`.
8. GitHub Actions commits `history.jsonl` back to `main`.
9. A success or failure email is sent after every run.

## Required GitHub Secrets

Add these in `Settings > Secrets and variables > Actions`.

### Gemini and Hugging Face

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

`META_ACCESS_TOKEN` and `FACEBOOK_PAGE_ACCESS_TOKEN` should use the production System User token generated in Meta Business Settings. `FACEBOOK_PAGE_ID` is the `Newscoo` page ID from `/me/accounts`, and `IG_USER_ID` is the linked `instagram_business_account.id`.

### Email Report

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
REPORT_EMAIL_TO
```

For Gmail SMTP:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<sender-gmail-address>
SMTP_PASSWORD=<gmail-app-password>
REPORT_EMAIL_TO=<recipient-email-address>
```

## Local Development

Create a virtual environment and install dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a local `.env` file when running outside GitHub Actions.

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

Run locally:

```bash
python3 main.py
```

Validate syntax before pushing changes:

```bash
python3 -m py_compile main.py
```

## Outputs

Every run writes generated assets under:

```text
outputs/YYYY-MM-DD/
```

Typical files:

```text
gemini_selected_result.txt
selected_news.txt
selected_articles.txt
instagram_captions.txt
sdxl_image_prompts.txt
generated_images.txt
failed_categories.txt
images/
```

GitHub Actions uploads `outputs/` as an artifact even if a later step fails.

Successful posts are recorded in:

```text
history.jsonl
```

`history.jsonl` is force-added by the workflow because local ignore rules may exclude generated runtime files, but production needs this file committed to prevent duplicate posting.

## Publishing Rules

An article is publishable only when all required content stages succeed:

- article body extraction
- Gemini caption generation
- SDXL image prompt generation
- Hugging Face image generation
- poster overlay rendering
- Cloudflare R2 upload
- `public_image_url` creation

If any primary article fails these checks, the backup article for the same category is processed. If both fail, the category is written to `failed_categories.txt`.

## Operational Notes

- The laptop does not need to be powered on. Runs happen on GitHub-hosted runners.
- Meta publishing uses a Meta Business System User token. If logs show `OAuthException`, `code 190`, or `Session has expired`, validate the System User token, assigned Page/Instagram assets, and GitHub Secrets before regenerating the token.
- Some publishers return `401` or `403` to automated article downloads. Those articles may fail body extraction and trigger backup processing.
- `trafilatura` can fail on specific HTML structures. The pipeline treats extraction failures as article-level failures rather than stopping the entire run.
- If fewer than 3 posts are published, inspect the run artifact files, especially `selected_articles.txt`, `generated_images.txt`, and `failed_categories.txt`.
- If `git push` is rejected after a workflow run, pull the latest `history.jsonl` commit first:

```bash
git pull --rebase origin main
git push origin main
```

## Common Commands

Check local state:

```bash
git status --short --branch
```

Commit workflow changes:

```bash
git add .github/workflows/daily-upload.yml
git commit -m "예약 실행 설정 조정"
git push origin main
```

Commit pipeline changes:

```bash
git add main.py
git commit -m "인스타 게시글 생성 프롬프트 개선"
git push origin main
```

Commit documentation changes:

```bash
git add README.md docs/architecture.jpeg
git commit -m "README 아키텍처 문서 추가"
git push origin main
```

## Safety

Never commit secrets:

```text
.env
```

The project uses official APIs instead of browser automation:

- Google Gemini API
- Hugging Face Inference API
- Cloudflare R2 S3-compatible API
- Meta Graph API
- SMTP

Users are responsible for complying with publisher policies, API provider terms, Meta Platform rules, and copyright requirements.
