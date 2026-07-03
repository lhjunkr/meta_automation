# Meta Automation

> Fully automated daily news-to-social pipeline. Collects news, curates with Gemini, generates Korean captions and poster images, and publishes to Instagram, Facebook, and Threads — hands-free, every morning.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white">
  <img alt="GitHub Actions" src="https://img.shields.io/badge/Runtime-GitHub_Actions-2088FF?logo=githubactions&logoColor=white">
  <img alt="Schedule" src="https://img.shields.io/badge/Schedule-06:23_KST_daily-16A34A">
  <img alt="License" src="https://img.shields.io/badge/Mode-DRY__RUN=false-DC2626">
</p>

<p>
  <img alt="Gemini" src="https://img.shields.io/badge/Google_Gemini-8E75B2?logo=googlegemini&logoColor=white">
  <img alt="Hugging Face" src="https://img.shields.io/badge/Hugging_Face-FFD21E?logo=huggingface&logoColor=black">
  <img alt="Cloudflare R2" src="https://img.shields.io/badge/Cloudflare_R2-F38020?logo=cloudflare&logoColor=white">
  <img alt="Instagram" src="https://img.shields.io/badge/Instagram-E4405F?logo=instagram&logoColor=white">
  <img alt="Facebook" src="https://img.shields.io/badge/Facebook-1877F2?logo=facebook&logoColor=white">
  <img alt="Threads" src="https://img.shields.io/badge/Threads-000000?logo=threads&logoColor=white">
</p>

---

## ✨ What it does

Every day at **06:23 KST**, GitHub Actions runs the full pipeline with zero manual input:

```
📰 Collect  →  🤖 Curate  →  ✍️ Caption  →  🎨 Render  →  ☁️ Upload  →  📤 Publish  →  📧 Report
```

| Stage | Powered by | Detail |
| --- | --- | --- |
| 📰 **Collect** | Google News | Gathers candidates, drops excluded sources and already-published articles |
| 🤖 **Curate** | Gemini | Picks one primary + one backup article per category |
| ✍️ **Caption** | Gemini → Qwen | Writes a Korean caption, with a Hugging Face fallback |
| 🎨 **Render** | FLUX + Pillow | Generates a poster image and overlays the news headline |
| ☁️ **Upload** | Cloudflare R2 | Stores the final poster at a public URL |
| 📤 **Publish** | Meta Graph API | Posts to Instagram, Facebook Page, and Threads |
| 📧 **Report** | SMTP + Artifacts | Emails a run summary and uploads outputs as CI artifacts |

Resilience is built in at every stage: image models, caption models, and body extractors each have a fallback chain, and a failing primary article is automatically replaced by its category backup.

---

## ⚙️ Production setup

The production runtime is **GitHub Actions** — the local machine never needs to be online.

| Item | Value |
| --- | --- |
| Workflow | `.github/workflows/daily-upload.yml` |
| Runtime | GitHub-hosted Ubuntu runner |
| Schedule | `23 21 * * *` UTC → **06:23 KST** |
| Manual run | `workflow_dispatch` (Actions tab) |
| Python | 3.11 |
| Publish mode | `DRY_RUN=false` |
| Daily post limit | `MAX_DAILY_POSTS=3` |
| Publish window | `UPLOAD_WINDOW_MINUTES=15` |
| Post spacing | `POST_SPACING_MINUTES=5` |
| Reporting | SMTP email + GitHub artifact |

**Run order:** checkout → install Python, Noto CJK fonts, and dependencies → CI quality gate (`ruff`, `mypy`, `unittest`) → write Secrets to `.env` → run `main.py`.

---

## 🧩 Modules

| File | Responsibility |
| --- | --- |
| `main.py` | Batch entry point |
| `models.py` | `Article` dataclass and dict compatibility helpers |
| `constants.py` | Centralized status strings |
| `time_utils.py` | KST-based date and time helpers |
| `config.py` | Environment-based runtime settings |
| `news.py` | Google News collection, URL resolution, body extraction |
| `content.py` | Gemini selection, primary/fallback Gemini text generation, Qwen caption fallback, image prompts |
| `image_generation.py` | Hugging Face image generation with model fallback |
| `image_rendering.py` | News poster overlay rendering |
| `storage.py` | Cloudflare R2 upload |
| `pipeline.py` | Content pipeline orchestration, completion checks, backup retry |
| `publishing.py` | Publish orchestration, preflight, daily limits, duplicate prevention |
| `instagram_publishing.py` | Instagram media container polling and publish |
| `facebook_publishing.py` | Facebook Page photo publish |
| `threads_publishing.py` | Threads media container polling and publish |
| `outputs.py` | Runtime output files |
| `reporting.py` | Run summary and failure report generation |
| `history.py` | Publish history and duplicate prevention |
| `tests/` | Unit tests for core model, pipeline, and rendering behavior |

---

## 🗂️ Data model

Article data is represented by `models.Article`.

<details>
<summary><b>Article fields</b></summary>

```text
id                          resolved_link               instagram_caption_model
category                    body                        sdxl_image_prompt
title                       instagram_caption           image_path
source                      final_image_path            public_image_url
google_link                 publish_status              instagram_publish_status
backup_article              facebook_publish_status     threads_publish_status
```

</details>

`Article.from_dict()` and `Article.to_dict()` keep compatibility with existing outputs and external inputs. Unknown fields are preserved in `extra_fields`, so schema changes never silently drop data.

---

## 🔁 Fallback strategies

Any single provider outage should not fail the whole run, so each generation step tries models in priority order.

**Image generation** (Hugging Face Inference API):

```text
1. black-forest-labs/FLUX.1-dev       · 28 steps · guidance 3.5
2. black-forest-labs/FLUX.1-schnell   ·  4 steps · guidance 0
3. black-forest-labs/FLUX.1-schnell   ·  4 steps · guidance 3.5
```

**Text generation** — Gemini selects article IDs, writes Korean captions, and generates SDXL image prompts. Every Gemini call uses a primary model, then retries once with the fallback model on retry-exhausted `429` or `503` errors. The caption model actually used is stored in `instagram_caption_model` and reported.

```text
1. gemini-3.5-flash
2. gemini-3.1-flash-lite
```

Korean caption generation additionally falls back to Hugging Face Qwen if both Gemini models fail:

```text
3. Qwen/Qwen2.5-72B-Instruct
```

**Body extraction:** `trafilatura` → `readability-lxml` → BeautifulSoup.

If all image models fail, the article gets `generation_failed` status and the pipeline moves to the category backup article.

---

## ✅ Publish eligibility

An article is published only when **all** of these succeed:

- ✔️ Body extraction
- ✔️ Caption generation
- ✔️ Image prompt generation
- ✔️ Hugging Face image generation
- ✔️ Poster rendering
- ✔️ R2 upload
- ✔️ `final_image_path` exists
- ✔️ `public_image_url` exists

If the primary article fails, the backup is processed. If both fail, the category is written to `failed_categories.txt`.

---

## 📤 Meta publishing

`publishing.py` runs a preflight check before sending any publish request.

**Required preflight** (blocks Instagram + Facebook if it fails):

- `META_ACCESS_TOKEN` can access `IG_USER_ID`
- `FACEBOOK_PAGE_ACCESS_TOKEN` can access `FACEBOOK_PAGE_ID`

**Threads preflight** — treated as an auxiliary channel:

- `THREADS_ACCESS_TOKEN` can access `THREADS_USER_ID`
- If it fails, Instagram and Facebook still publish; the Threads error is written to the article status and email report.

> **Tip:** For long-term operation, use a Meta Business System User token with the required Page and Instagram assets assigned. Instagram and Facebook credentials are split intentionally so each channel can be rotated or debugged independently. Threads uses a separate long-lived token that should be refreshed before expiration.

---

## 📦 Runtime outputs

Every run writes outputs under a KST date folder: `outputs/YYYY-MM-DD/`.

```text
gemini_selected_result.txt    instagram_captions.txt      run_report.txt
selected_news.txt             sdxl_image_prompts.txt      failed_categories.txt
selected_articles.txt         generated_images.txt        failure_report.txt   images/
```

- **`run_report.txt`** — channel upload counts, uploaded titles, caption/image model names, and channel post IDs.
- **`failure_report.txt`** — category, article, and publishing failures.
- Both reports are included in the email body; all `outputs/**/*.txt` files are attached to the email and uploaded as GitHub Actions artifacts.

**Publish history** is appended locally to `history.jsonl` (URLs, social post IDs, public image URLs). It is Git-ignored and must not be committed to a public repo. At the start of each run, recent history is downloaded from a private R2 key so duplicate prevention and daily-limit counting work across runs. Remote history lives separately from public posters at `private/history/YYYY-MM-DD/history.jsonl`, with a 3-day retention window matching local outputs.

---

## 🔐 Required GitHub Secrets

Add these under `Settings → Secrets and variables → Actions`.

<details>
<summary><b>Gemini / Hugging Face</b></summary>

```text
GEMINI_API_KEY
HF_TOKEN
```

</details>

<details>
<summary><b>Cloudflare R2</b></summary>

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_PUBLIC_BASE_URL
```

</details>

<details>
<summary><b>Meta / Instagram / Facebook</b></summary>

```text
META_ACCESS_TOKEN              = Meta Business System User token
IG_USER_ID                     = Instagram Business Account ID
FACEBOOK_PAGE_ID               = Facebook Page ID
FACEBOOK_PAGE_ACCESS_TOKEN     = Page access token from /me/accounts
```

The System User must have access to the Facebook Page, Instagram Business Account, and Meta app. Required permissions typically include `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_metadata`, `instagram_basic`, and `instagram_content_publish`.

</details>

<details>
<summary><b>Threads</b></summary>

```text
THREADS_ACCESS_TOKEN     = long-lived Threads token for the target profile
THREADS_USER_ID          = Threads profile ID from the Threads Graph API
```

</details>

<details>
<summary><b>Email report (Gmail SMTP example)</b></summary>

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<sender-gmail-address>
SMTP_PASSWORD=<gmail-app-password>
REPORT_EMAIL_TO=<recipient-email-address>
```

</details>

---

## 💻 Local development

```bash
# 1. Create a virtual environment and install production deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Install dev deps (lint, type check, tests)
pip install -r requirements-dev.txt
```

Create a local `.env` for local execution:

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

THREADS_ACCESS_TOKEN=
THREADS_USER_ID=

MAX_DAILY_POSTS=3
UPLOAD_WINDOW_MINUTES=15
POST_SPACING_MINUTES=5
```

> Production values are managed through GitHub Actions Secrets. If local `.env` values differ, local publish verification is not authoritative.

---

## 🧪 Quality checks

```bash
# Full local check
python3 -m ruff check .
python3 -m mypy .
python3 -m unittest discover -s tests
```

<details>
<summary><b>Syntax-only compile check</b></summary>

```bash
python3 -m py_compile main.py models.py constants.py reporting.py pipeline.py \
  image_generation.py content.py news.py image_rendering.py storage.py outputs.py \
  publishing.py history.py config.py time_utils.py instagram_publishing.py \
  facebook_publishing.py threads_publishing.py
```

</details>

---

## 🛠️ Operations notes

- Runs on GitHub-hosted runners — your laptop does not need to be online.
- Output folders, poster dates, and daily post limits all use **KST**.
- With `DRY_RUN=false`, a manual dispatch publishes **real** Instagram, Facebook, and Threads posts.
- Publish timing is controlled by `UPLOAD_WINDOW_MINUTES` and `POST_SPACING_MINUTES`.
- Some publishers return `401`, `402`, or `403` during article body download — this is expected and handled by the extractor fallback chain.
- If Meta returns `OAuthException`, `code 190`, or `Session has expired`, check the System User token, Threads token, asset assignments, and GitHub Secrets first.

---

## 🔒 Security

Never commit these files (both are Git-ignored):

```text
.env             # credentials
history.jsonl    # runtime history with URLs and post IDs
```

This project uses official APIs only: **Google Gemini**, **Hugging Face Inference**, **Cloudflare R2 (S3-compatible)**, **Meta Graph**, **Threads Graph**, and **SMTP**.

Operators are responsible for complying with publisher policies, provider terms, Meta Platform policies, and copyright requirements.
