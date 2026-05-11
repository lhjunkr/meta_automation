# News-to-Social Automation Pipeline

### Google News → Gemini → SDXL → Cloudflare R2 → Meta Graph API

A Python-based automation pipeline that transforms daily news into localized Instagram and Facebook content. The system collects news candidates, selects articles with Gemini, extracts article bodies, generates Korean captions, creates poster images, uploads final images to Cloudflare R2, and publishes through the official Meta Graph API.

> Current status: the main pipeline is implemented, Cloudflare R2 upload has been tested, and manual Instagram/Facebook posting through Meta Graph API has succeeded. Full production hardening such as token refresh, deployment scheduling, monitoring, and alerting is still pending.

---

## System Logic

The project is designed around four stages of social content production:

1. **Discovery**: collect fresh news candidates.
2. **Curation**: select relevant articles with Gemini.
3. **Creation**: generate captions and poster images.
4. **Distribution**: publish through official Meta APIs.

The publishing flow avoids browser automation and uses the Meta Graph API for Instagram and Facebook posting.

---

## Architecture & Workflow

| Phase | Process | Technology |
| --- | --- | --- |
| 1. Ingestion | Collect Google News candidates and deduplicate articles | `pygooglenews`, `history.jsonl` |
| 2. Filtering | Exclude already-used links and configured news sources | `history.jsonl`, source keyword filters |
| 3. Selection | Select primary/backup articles by category | `Google Gemini` |
| 4. Extraction | Resolve Google News links and extract article body text | `googlenewsdecoder`, `requests`, `trafilatura` |
| 5. Captioning | Generate Korean Instagram/Facebook captions | `Google Gemini` |
| 6. Image Prompting | Generate SDXL image prompts | `Google Gemini` |
| 7. Image Generation | Create poster images | `Hugging Face Inference API`, `SDXL` |
| 8. Composition | Add Korean headline, source, date, and gradient overlay | `Pillow` |
| 9. Hosting | Upload final images to public object storage | `Cloudflare R2`, `boto3` |
| 10. Publishing | Publish to Instagram and Facebook | `Meta Graph API` |
| 11. History | Record successful posts and clean old outputs | `history.jsonl`, `outputs/` |

---

## Tech Stack

- Python 3.10+
- Google Gemini API
- Hugging Face Inference API
- Stable Diffusion XL
- Cloudflare R2
- Meta Graph API
- `pygooglenews`
- `googlenewsdecoder`
- `requests`
- `trafilatura`
- `Pillow`
- `boto3`
- `python-dotenv`

---

## Requirements

You need accounts and credentials for:

- Google Gemini API
- Hugging Face
- Cloudflare R2
- Meta Developer App
- Instagram Professional account
- Facebook Page connected to the Instagram account

---

## Environment Variables

Create a `.env` file from `.env.example`.

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
MIN_POST_INTERVAL_MINUTES=90
POST_JITTER_MINUTES_MIN=5
POST_JITTER_MINUTES_MAX=25
```

Never commit `.env` to Git.

---

## Quick Start

1. Clone the repository.

```bash
git clone <repo-url>
cd <repo-folder>
```

2. Create and activate a virtual environment.

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create your environment file.

```bash
cp .env.example .env
```

5. Fill in the required API keys and account IDs in `.env`.

6. Run the pipeline.

```bash
python3 main.py
```

---

## Output Structure

Generated files are stored under:

```text
outputs/YYYY-MM-DD/
```

Typical output files:

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

Successful published articles are recorded in:

```text
history.jsonl
```

---

## Publishing Flow

Instagram publishing uses the official two-step Meta Graph API flow:

1. Create a media container.
2. Publish the media container.

Facebook Page publishing uses the Page photos endpoint.

Images must be publicly accessible before publishing. This project uploads final poster images to Cloudflare R2 and uses the public R2 URL for Meta publishing.

---

## Operational Guardrails

The project includes basic operational controls:

- `MAX_DAILY_POSTS`: limits the number of posts per day.
- `MIN_POST_INTERVAL_MINUTES`: enforces spacing between posts.
- `POST_JITTER_MINUTES_MIN` / `POST_JITTER_MINUTES_MAX`: adds randomized delay before publishing.
- `history.jsonl`: prevents duplicate article/image publishing.
- `outputs/`: keeps local generated files organized by date.

Publishing is done through the official Meta Graph API. The project does not use browser automation or unofficial Instagram automation.

---

## Git Hygiene

Do not commit secrets or generated outputs.

Recommended ignored files:

```gitignore
.env
venv/
__pycache__/
outputs/
generated_images/
*.txt
history.jsonl
history.txt
```

---

## Roadmap

Planned hardening work:

- Long-lived Meta token refresh strategy
- Deployment scheduling with cron, server runner, or CI/CD
- Structured logging
- Error reporting and alerting
- Retry policy for external API failures
- Human review step before publishing
- Improved image quality control
- Better post-run reporting

---

## Disclaimer

This project is a functional automation prototype, not a fully hardened production system. Users are responsible for complying with news source copyright policies, API provider terms, and Meta platform rules.
