# Groww Weekly Review Pulse

An automated, scheduled intelligence pipeline that fetches App Store and Play Store reviews for Groww, uses LLMs to group reviews into core themes, and emails a one-page "Weekly Pulse Note" PDF.

This project is built to run entirely on free-tier services (GitHub Actions, Groq API, Gemini API, Gmail SMTP).

## 🚀 Features
- **Automated Scraping:** Pulls latest reviews from Google Play and Apple App Store.
- **Smart Filtering:** Prioritizes recency, low ratings, and historical comparisons.
- **LLM Insights:** Uses Groq (LLaMA 3.1 8B) for clustering themes and Gemini Flash 1.5 for drafting summaries and actionable product ideas.
- **Trend Analysis:** Computes week-over-week sentiment trends and >30% theme spike alerts.
- **PDF Generation:** Creates a single-page, cleanly formatted PDF report using ReportLab.
- **Automated Delivery:** Sends via email and archives the snapshot in GitHub for future baseline processing.

## 🛠️ Setup Instructions

### 1. Clone & Install
```bash
git clone <repository_url>
cd groww-review-pulse
python -m venv venv
source venv/Scripts/activate  # On macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables
Copy the example environment file and fill in your details:
```bash
cp .env.example .env
```

Required variables:
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `RECIPIENT_EMAIL`

## 🏃‍♂️ Running Locally

The pipeline is split into 5 modules. To test the pipeline, execute them sequentially from the root directory:

```bash
# Stage 1: Fetch raw reviews
python -m pipeline.fetch_reviews

# Stage 2: Filter and select top 80 reviews
python -m pipeline.clean_and_rank

# Stage 3: Generate themes via Groq
python -m pipeline.theme_engine

# Stage 4: Draft summary and generate PDF via Gemini
python -m pipeline.pulse_generator

# Stage 5: Send email (will only commit snapshot if run inside CI)
python -m pipeline.deliver_and_commit
```

## ☁️ Deployment (GitHub Actions)

The pipeline is configured to run automatically every Monday at 6 AM IST (00:30 UTC) using GitHub Actions.

1. Ensure the `.github/workflows/weekly_pulse.yml` is present in the default branch.
2. Go to your repository settings -> **Secrets and variables** -> **Actions**.
3. Add the 5 secrets listed in the Environment Variables section.
4. Ensure GitHub Actions has **Read and write permissions** for workflows so it can commit the `snapshots/` JSON files back to the repository.
