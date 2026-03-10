import sys
import os
import json
from datetime import datetime

# Ensure we can import config from the parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    from google_play_scraper import Sort, reviews
except ImportError:
    print("Warning: google-play-scraper not found. Install it for full functionality.")

try:
    from app_store_scraper import AppStore
except ImportError:
    print("Warning: app-store-scraper not found. Install it for full functionality.")


def get_play_store_reviews(target_count=1000):
    print(f"Fetching up to {target_count} Play Store reviews...")
    try:
        result, _ = reviews(
            config.PLAY_STORE_APP_ID,
            lang='en',
            country='in',
            sort=Sort.NEWEST,
            count=target_count
        )
        
        cleaned = []
        for r in result:
            # Safely handle dates
            dt = r.get("at")
            if isinstance(dt, datetime):
                iso_date = dt.isoformat()
            else:
                iso_date = str(dt) if dt else ""

            cleaned.append({
                "source": "playstore",
                "rating": int(r.get("score")),
                "title": "",  # Play store typically lacks a separate title field
                "text": str(r.get("content", "")).strip(),
                "date": iso_date
            })
        print(f"Successfully fetched {len(cleaned)} Play Store reviews.")
        return cleaned
    except Exception as e:
        print(f"Error fetching Play Store reviews: {e}")
        return []


def get_app_store_reviews(target_count=1000):
    print(f"Fetching up to {target_count} App Store reviews...")
    try:
        # AppStore logs a lot to stdout, wait for it to finish
        app = AppStore(country=config.APP_STORE_COUNTRY, app_name='groww', app_id=config.APP_STORE_APP_ID)
        app.review(how_many=target_count)
        
        cleaned = []
        for r in app.reviews:
            # Safely handle dates
            dt = r.get("date")
            if isinstance(dt, datetime):
                iso_date = dt.isoformat()
            else:
                iso_date = str(dt) if dt else ""

            cleaned.append({
                "source": "appstore",
                "rating": int(r.get("rating")),
                "title": str(r.get("title", "")).strip(),
                "text": str(r.get("review", "")).strip(),
                "date": iso_date
            })
        print(f"Successfully fetched {len(cleaned)} App Store reviews.")
        return cleaned
    except Exception as e:
        print(f"Error fetching App Store reviews: {e}")
        return []


def main():
    # Ensure intermediate outputs directory exists
    os.makedirs(os.path.dirname(config.RAW_REVIEWS_PATH), exist_ok=True)
    
    print("Starting Stage 1: fetch_reviews.py")
    
    # We fetch a larger amount to ensure we get enough history for 8 weeks
    # Filtering enforces the limits in Stage 2
    play_reviews = get_play_store_reviews(target_count=1000)
    app_reviews = get_app_store_reviews(target_count=500)
    
    all_reviews = play_reviews + app_reviews
    
    # Save to JSON
    with open(config.RAW_REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_reviews, f, indent=2, ensure_ascii=False)
        
    print(f"Saved a total of {len(all_reviews)} reviews to {config.RAW_REVIEWS_PATH}")
    print("Stage 1 completed successfully.")

if __name__ == "__main__":
    main()
