# Groww Weekly Review Pulse - Architecture

## 🎯 Goal
A scheduled pipeline that fetches App Store and Play Store reviews for Groww, uses LLMs to extract themes and sentiment, and emails a one-page "Weekly Pulse Note" PDF. Runs every Monday at 6 AM IST via GitHub Actions free tier.

## 🏗️ Pipeline Architecture

The pipeline is split into 5 strictly modular stages. Each stage is an independent Python script that reads from and writes to local JSON files (`outputs/` directory) to enable easy debugging, state management, and graceful degradation.

### Stage 1: `fetch_reviews.py`
**Goal:** Scrape recent reviews from both app stores without restriction on counts (to ensure we have enough historical data for the trend comparison).
- **Action:** Scrapes Groww reviews from Google Play Store (`com.nextbillion.msalary`) and Apple App Store (`Groww`).
- **Data Extracted:** `rating`, `title`, `text`, `date`, `source`.
- **Anonymization:** Strips PII (no reviewer name, ID, or handle).
- **Scale:** Fetches enough reviews crossing the last 8 weeks (no strict 200 limit here since scraping is free; filtering happens in Stage 2).
- **Output:** `outputs/raw_reviews.json`

### Stage 2: `clean_and_rank.py`
**Goal:** Filter, distribute, and rank top reviews to fit within LLM token/cost limits.
- **Action:** Loads `raw_reviews.json`.
- **Filtering Logic (200 reviews selected for distribution):**
  - Last 2 weeks: 100 reviews (recency signal)
  - Weeks 3–5: 60 reviews (trend signal)
  - Weeks 6–8: 40 reviews (baseline comparison)
- **Distribution Rules (within each band):**
  - 60% Play Store / 40% App Store
  - 60% Lowest rated (1-2 stars) / 40% Mid-High rated (3-5 stars)
- **Selection:** Ranks and selects the **Top 80 reviews** (Prioritizing most recent + lowest rating).
- **Output:** `outputs/ranked_reviews.json`

### Stage 3: `theme_engine.py` [LLM Call 1: Groq - LLaMA 3.1 8B]
**Goal:** Extract 3-5 key themes from the filtered reviews.
- **Action:** Sends `ranked_reviews.json` to Groq.
- **Processing:** Includes a strict prompt for Groq to return JSON containing themes.
- **Data Structure:** Each theme includes `theme_name`, `review_count`, `representative_quotes` (2-3 anonymized), and `sentiment_score` (0.0 - 1.0).
- **Resilience:** Cleans Markdown formatting from LLM output. Validates against a strict `pydantic` schema. Retries up to 2 times on validation failure.
- **Output:** `outputs/themes.json`

### Stage 4: `pulse_generator.py` [LLM Call 2: Gemini Flash 1.5]
**Goal:** Generate the pulse note summary and PDF.
- **Action:** Loads `themes.json` and the previous week's snapshot from `snapshots/`.
- **Computation:**
  - **Sentiment Trend:** Average sentiment vs. last week.
  - **Spike Alert:** Flags any theme with >30% volume increase WoW.
  - *Cold Start Handling:* Gracefully handles Week 1 where no prior snapshot exists.
- **LLM Processing:** Calls Gemini Flash to draft a ≤250-word synthesis containing the Top 3 themes, 3 quotes, and 3 actionable product ideas. Drafts the email body.
- **PDF Generation:** Uses `reportlab` to render the single-page, scannable PDF.
- **Output:** `outputs/pulse_note.json` and `outputs/weekly_pulse.pdf`

### Stage 5: `deliver_and_commit.py`
**Goal:** Distribute the report and save state.
- **Action:** 
  - Emails the draft and PDF via Gmail SMTP using App Passwords.
  - Commits `themes.json` contents and metadata to `snapshots/YYYY-WW.json` via GitHub Actions.
- **Resilience:** If Stage 3 or 4 fails, it reads the previous week's snapshot, flags the email with "⚠️ Data Pending", and ensures an email is still sent.

## 📂 Repository Structure
```text
groww-review-pulse/
├── .github/
│   └── workflows/
│       └── weekly_pulse.yml       # Cron job definition (schedule: '30 0 * * 1' for 6AM IST)
├── pipeline/
│   ├── __init__.py
│   ├── fetch_reviews.py           # Stage 1: Scraping 
│   ├── clean_and_rank.py          # Stage 2: Filtering and selecting top 80
│   ├── theme_engine.py            # Stage 3: Groq LLM parsing (Call 1)
│   ├── pulse_generator.py         # Stage 4: Gemini LLM text & ReportLab PDF (Call 2)
│   └── deliver_and_commit.py      # Stage 5: SMTP delivery & GitHub commit
├── snapshots/
│   └── .gitkeep                   # Persisted historical snapshots (YYYY-WW.json)
├── outputs/
│   └── .gitkeep                   # Local temp folder for intermediate JSONs & PDFs
├── config.py                      # Constants, limits, and env variable mappings
├── requirements.txt               # Pinned dependencies
├── .env.example                   # Template for local secrets
├── .gitignore                     # Ignore local .env, __pycache__, and temp outputs
├── README.md                      # Setup and run instructions
└── architecture.md                # System design and constraints
```

## 🔐 Environment Variables & Secrets
- `GROQ_API_KEY`: For LLaMA 3.1 inference.
- `GEMINI_API_KEY`: For summary generation.
- `GMAIL_ADDRESS`: Sender email address.
- `GMAIL_APP_PASSWORD`: SMTP app password.
- `RECIPIENT_EMAIL`: Comma-separated or single email string for delivery.
