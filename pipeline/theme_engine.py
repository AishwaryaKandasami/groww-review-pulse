import os
import sys
import json
import re
from typing import List
from pydantic import BaseModel, ValidationError, Field

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    from groq import Groq
except ImportError:
    print("Error: 'groq' not installed. Run 'pip install groq pydantic'")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --- Pydantic Schemas for Strict Output Validation ---
class Theme(BaseModel):
    theme_name: str = Field(description="A short, descriptive name for the theme (e.g., 'App Crashes on Login')")
    review_count: int = Field(description="The approximate number of reviews that fall under this theme")
    sentiment_score: float = Field(description="Average sentiment for this theme, from 0.0 (very negative) to 1.0 (very positive)")
    representative_quotes: List[str] = Field(description="2 to 3 direct, anonymized quotes from the reviews that highlight the theme")

class ThemesResponse(BaseModel):
    themes: List[Theme] = Field(description="List of 3 to 5 core themes extracted from the reviews")


def load_ranked_reviews():
    if not os.path.exists(config.RANKED_REVIEWS_PATH):
        print(f"Error: {config.RANKED_REVIEWS_PATH} not found. Run Stage 2 first.")
        sys.exit(1)
    with open(config.RANKED_REVIEWS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json_response(raw_response: str) -> str:
    """Removes markdown formatting (like ```json ... ```) from LLM output."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
        
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
        
    return cleaned.strip()


def extract_themes(reviews, client: Groq):
    """Sends reviews to Groq and parses/validates the JSON output."""
    
    # Format reviews for the prompt
    reviews_text = "\n\n".join(
        [f"Rating: {r.get('rating')}/5\nStore: {r.get('source')}\nReview: {r.get('text')}" 
         for r in reviews]
    )

    prompt = f"""
    You are an expert Product Manager analyzing mobile app reviews for Groww (a financial & investment app).
    Analyze the following {len(reviews)} recent and highly critical user reviews.
    
    Your task is to group these reviews into 3 to {config.MAX_THEMES} distinct product themes.
    Focus on specific friction points, bugs, or feature requests. Do not create vague themes like "General Feedback".
    
    For each theme, provide:
    1. A short, highly descriptive theme_name.
    2. The review_count (approximate number of reviews mapping to this theme).
    3. A sentiment_score from 0.0 (completely negative) to 1.0 (completely positive). **CRITICAL:** Do NOT default to 0.0. Calculate a reasonable average (e.g., if reviews are mostly 1-star but some are 3-star, the score should be around 0.2 or 0.3. A score of 0.0 means every single word is pure hatred, which is rare).
    4. representative_quotes: 2-3 direct quotes from users (strip out any names or PII).

    You MUST return ONLY a valid JSON object matching this schema, and nothing else. DO NOT wrap the JSON in markdown formatting (like ```json), just output the raw JSON object itself:
    {{
        "themes": [
            {{
                "theme_name": "string",
                "review_count": "integer",
                "sentiment_score": "float",
                "representative_quotes": ["string", "string"]
            }}
        ]
    }}
    
    Reviews to analyze:
    {reviews_text}
    """

    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            print(f"Calling Groq API (Attempt {attempt + 1}/{config.LLM_MAX_RETRIES})...")
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a specialized data extractor that outputs only raw, valid JSON. Never output markdown, introductory text, or explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, # Low temperature for more deterministic/consistent output
                response_format={"type": "json_object"} # Force JSON mode if available
            )
            
            raw_content = response.choices[0].message.content
            cleaned_json = clean_json_response(raw_content)
            
            # Parse and validate with Pydantic
            parsed_data = json.loads(cleaned_json)
            validated_data = ThemesResponse(**parsed_data)
            
            return validated_data.model_dump()
            
        except json.JSONDecodeError as j_err:
            print(f"JSON Parsing Error on attempt {attempt + 1}: {j_err}")
            print(f"Raw Output: {raw_content}")
        except ValidationError as v_err:
            print(f"Schema Validation Error on attempt {attempt + 1}: {v_err}")
            print(f"Parsed JSON: {parsed_data}")
        except Exception as e:
            print(f"API/Network Error on attempt {attempt + 1}: {e}")
            
    return None


def fallback_to_last_week():
    """If Groq fails entirely, try loading last week's snapshots as a fallback."""
    print("Determining fallback from historical snapshots...")
    import glob
    
    snapshots = sorted(glob.glob(os.path.join(config.SNAPSHOT_DIR, "*.json")))
    if not snapshots:
        print("No historical snapshots found to fallback to.")
        return None
        
    latest_snapshot = snapshots[-1]
    print(f"Falling back to {latest_snapshot}")
    
    try:
        with open(latest_snapshot, "r", encoding="utf-8") as f:
            data = json.load(f)
            # A valid snapshot contains themes inside the pulse or root. We expect 'themes'.
            if "themes" in data:
                return {"themes": data["themes"], "is_fallback": True}
    except Exception as e:
        print(f"Failed to read fallback snapshot error: {e}")
        
    return None


def main():
    print("Starting Stage 3: theme_engine.py")
    
    api_key = os.getenv(config.ENV_GROQ_API_KEY)
    if not api_key:
        print(f"Error: {config.ENV_GROQ_API_KEY} environment variable is not set.")
        sys.exit(1)

    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        print(f"Failed to initialize Groq client: {e}")
        sys.exit(1)
        
    ranked_reviews = load_ranked_reviews()
    
    if not ranked_reviews:
        print("Error: No ranked reviews found. Nothing to process.")
        sys.exit(1)
        
    print(f"Loaded {len(ranked_reviews)} reviews for LLM processing.")
    
    themes_output = extract_themes(ranked_reviews, client)
    
    if not themes_output:
        print("Warning: Groq API failed after max retries. Attempting fallback...")
        themes_output = fallback_to_last_week()
        
        if not themes_output:
            print("CRITICAL: Groq processing failed and no fallback available.")
            sys.exit(1)
            
    # Save output
    os.makedirs(os.path.dirname(config.THEMES_PATH), exist_ok=True)
    with open(config.THEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(themes_output, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully processed {len(themes_output.get('themes', []))} themes.")
    print(f"Saved to {config.THEMES_PATH}")
    print("Stage 3 completed successfully.")


if __name__ == "__main__":
    main()
