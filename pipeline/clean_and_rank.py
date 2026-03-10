import os
import sys
import json
from datetime import datetime, timezone, timedelta

# Ensure config can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def load_raw_reviews():
    if not os.path.exists(config.RAW_REVIEWS_PATH):
        print(f"Error: {config.RAW_REVIEWS_PATH} not found. Run Stage 1 first.")
        sys.exit(1)
    
    with open(config.RAW_REVIEWS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def categorize_by_age(reviews, now):
    """Sorts reviews into the 3 defined time bands (in weeks)."""
    bands = {"recent": [], "mid": [], "base": []}
    
    for r in reviews:
        if not r.get("date"):
            continue
            
        try:
            # Handle standard ISO formats, removing 'Z' if present
            date_str = r["date"].replace("Z", "+00:00")
            r_date = datetime.fromisoformat(date_str)
            # Ensure aware datetime for comparison
            if r_date.tzinfo is None:
                r_date = r_date.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
            
        age_days = (now - r_date).days
        
        # 0 to 2 weeks
        if age_days <= (config.BAND_RECENT_WEEKS * 7):
            bands["recent"].append(r)
        # 2 to 5 weeks
        elif age_days <= ((config.BAND_RECENT_WEEKS + config.BAND_MID_WEEKS) * 7):
            bands["mid"].append(r)
        # 5 to 8 weeks
        elif age_days <= ((config.BAND_RECENT_WEEKS + config.BAND_MID_WEEKS + config.BAND_BASE_WEEKS) * 7):
            bands["base"].append(r)
            
    return bands


def sample_band(band_reviews, target_count):
    """
    Given a list of reviews in a specific age band, sample them according to:
      1. Store split (60% Play Store, 40% App Store)
      2. Rating split (70% Low, 30% Mid/High) inside each store
    """
    if not band_reviews:
        return []
        
    play_reviews = [r for r in band_reviews if r.get("source") == "playstore"]
    app_reviews = [r for r in band_reviews if r.get("source") == "appstore"]
    
    # Calculate target counts
    play_target = int(target_count * config.PLAY_STORE_RATIO)
    app_target = int(target_count * config.APP_STORE_RATIO)
    
    # Adjust targets if one store is short (due to API issues or low volume)
    if len(app_reviews) < app_target:
        shortfall = app_target - len(app_reviews)
        play_target += shortfall
        app_target = len(app_reviews)
        
    if len(play_reviews) < play_target:
        shortfall = play_target - len(play_reviews)
        app_target += shortfall
        play_target = len(play_reviews)
        
    def filter_rating(reviews, max_target):
        if not reviews:
            return []
            
        low_rated = [r for r in reviews if r.get("rating", 5) <= config.LOW_RATING_MAX]
        high_rated = [r for r in reviews if r.get("rating", 0) > config.LOW_RATING_MAX]
        
        low_target = int(max_target * config.LOW_RATING_RATIO)
        high_target = max_target - low_target
        
        # Adjust if short
        if len(low_rated) < low_target:
            high_target += (low_target - len(low_rated))
            low_target = len(low_rated)
            
        if len(high_rated) < high_target:
            low_target += (high_target - len(high_rated))
            high_target = len(high_rated)
            
        sampled = low_rated[:low_target] + high_rated[:high_target]
        return sampled

    sampled_play = filter_rating(play_reviews, play_target)
    sampled_app = filter_rating(app_reviews, app_target)
    
    return sampled_play + sampled_app


def rank_and_slice(sampled_reviews):
    """
    Sorts all sampled reviews across bands.
    Priority 1: Most recent
    Priority 2: Lowest rating
    Then slices to the strict LLM input limit (80)
    """
    
    def sorting_key(review):
        # We need to sort by recency (highest date first) AND rating (lowest first)
        # To do this in one pass: 
        #   Rating ascending (1 -> 5)
        #   Date descending (future -> past)
        # We can't mix asc/desc numeric directly easily on mixed types, 
        # so we sort twice or use a tuple with inverted timestamps.
        
        rating = review.get("rating", 5)
        
        date_str = review.get("date", "1970-01-01T00:00:00+00:00")
        try:
            date_str = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            timestamp = dt.timestamp()
        except Exception:
            timestamp = 0
            
        # Primary: Rating (ascending: 1 stars first)
        # Secondary: Recency (descending: newer timestamps first, so we use negative timestamp)
        return (rating, -timestamp)

    sampled_reviews.sort(key=sorting_key)
    
    # Hard cap for LLM
    return sampled_reviews[:config.LLM_INPUT_LIMIT]


def main():
    print("Starting Stage 2: clean_and_rank.py")
    
    raw_reviews = load_raw_reviews()
    print(f"Loaded {len(raw_reviews)} raw reviews.")
    
    now = datetime.now(timezone.utc)
    
    # 1. Categorize by Age
    bands = categorize_by_age(raw_reviews, now)
    print(f"Age breakdown - Recent: {len(bands['recent'])}, "
          f"Mid: {len(bands['mid'])}, Base: {len(bands['base'])}")
    
    # 2. Sample within bands (Applying store & rating distribution)
    sampled_recent = sample_band(bands['recent'], config.BAND_RECENT_COUNT)
    sampled_mid = sample_band(bands['mid'], config.BAND_MID_COUNT)
    sampled_base = sample_band(bands['base'], config.BAND_BASE_COUNT)
    
    total_sampled = sampled_recent + sampled_mid + sampled_base
    print(f"Total reviews after stratified sampling: {len(total_sampled)} (Target: {config.STRATIFIED_TOTAL})")
    
    # 3. Rank by Recency & Lowest Rating, then slice to Top 80
    final_ranked = rank_and_slice(total_sampled)
    
    # Save output
    os.makedirs(os.path.dirname(config.RANKED_REVIEWS_PATH), exist_ok=True)
    with open(config.RANKED_REVIEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(final_ranked, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully saved {len(final_ranked)} LLM-ready "
          f"reviews to {config.RANKED_REVIEWS_PATH}")
    print("Stage 2 completed successfully.")


if __name__ == "__main__":
    main()
