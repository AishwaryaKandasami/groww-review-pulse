import os
from pathlib import Path

# --- App Identifiers ---
PLAY_STORE_APP_ID = "com.nextbillion.groww"      # updated from msalary
APP_STORE_APP_ID = "1404263591"          # Groww's App Store ID
APP_STORE_COUNTRY = "in"                 # India store only

# --- Data Limits ---
MAX_FETCH_WEEKS = 8                      # rolling window for fetch
STRATIFIED_TOTAL = 200                   # max reviews after sampling
LLM_INPUT_LIMIT = 80                     # max reviews sent to LLM
MAX_THEMES = 5
REPORT_TOP_THEMES = 3
SPIKE_ALERT_THRESHOLD = 0.30             # 30% WoW volume increase

# --- Time Band Sampling (stratified) ---
BAND_RECENT_WEEKS = 2                    # weeks 1–2  -> 100 reviews
BAND_MID_WEEKS = 3                       # weeks 3–5  -> 60 reviews
BAND_BASE_WEEKS = 3                      # weeks 6–8  -> 40 reviews
BAND_RECENT_COUNT = 100
BAND_MID_COUNT = 60
BAND_BASE_COUNT = 40

# --- Store Split per Band ---
PLAY_STORE_RATIO = 0.60                  # 60% from Play Store
APP_STORE_RATIO = 0.40                   # 40% from App Store

# --- Rating Split per Band ---
LOW_RATING_RATIO = 0.70                  # 70% from 1–2 star reviews
MID_HIGH_RATIO = 0.30                    # 30% from 3–5 star reviews
LOW_RATING_MAX = 2                       # defines "low rating" threshold

# --- LLM Config ---
GROQ_MODEL = "llama-3.1-8b-instant"
GEMINI_MODEL = "gemini-2.5-flash"
LLM_MAX_RETRIES = 2
PULSE_MAX_WORDS = 250

# --- File Paths ---
RAW_REVIEWS_PATH = "outputs/raw_reviews.json"
RANKED_REVIEWS_PATH = "outputs/ranked_reviews.json"
THEMES_PATH = "outputs/themes.json"
PULSE_NOTE_PATH = "outputs/pulse_note.json"
PDF_OUTPUT_PATH = "outputs/weekly_pulse.pdf"
SNAPSHOT_DIR = "snapshots/"

# --- Email Config ---
EMAIL_SUBJECT_PREFIX = "Groww Weekly Review Pulse — Week of"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587                          # STARTTLS, not SSL

# --- Env Variable Names (strings only) ---
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_GMAIL_ADDRESS = "GMAIL_ADDRESS"
ENV_GMAIL_APP_PASSWORD = "GMAIL_APP_PASSWORD"
ENV_RECIPIENT_EMAIL = "RECIPIENT_EMAIL"
