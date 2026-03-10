import os
import sys
import json
import glob
from datetime import datetime, timezone

# Ensure config can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import google.generativeai as genai
except ImportError:
    print("Error: 'google-generativeai' not installed. Run 'pip install google-generativeai'")
    sys.exit(1)

try:
    import matplotlib.pyplot as plt
    import io
    import base64
except ImportError:
    print("Error: 'matplotlib' not installed. Run 'pip install matplotlib'")
    sys.exit(1)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
except ImportError:
    print("Error: 'reportlab' not installed. Run 'pip install reportlab'")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_themes():
    if not os.path.exists(config.THEMES_PATH):
        print(f"Error: {config.THEMES_PATH} not found. Run Stage 3 first.")
        sys.exit(1)
    with open(config.THEMES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("themes", [])


def load_previous_snapshot():
    snapshots = sorted(glob.glob(os.path.join(config.SNAPSHOT_DIR, "*.json")))
    if not snapshots:
        return None
        
    latest_snapshot = snapshots[-1]
    try:
        with open(latest_snapshot, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading snapshot {latest_snapshot}: {e}")
        return None


def compute_metrics(current_themes, previous_snapshot):
    curr_avg_sentiment = 0.0
    if current_themes:
        curr_avg_sentiment = sum(t.get("sentiment_score", 0.0) for t in current_themes) / len(current_themes)
        
    metrics = {
        "current_sentiment": curr_avg_sentiment,
        "sentiment_trend": "No prior data for WoW comparison",
        "spike_alerts": []
    }
    
    # Cold Start handling: Week 1 has no previous snapshot
    if not previous_snapshot or "themes" not in previous_snapshot:
        return metrics
        
    prev_themes = previous_snapshot.get("themes", [])
    prev_avg_sentiment = 0.0
    if prev_themes:
        prev_avg_sentiment = sum(t.get("sentiment_score", 0.0) for t in prev_themes) / len(prev_themes)
        
    # Sentiment trend vs last week
    diff = curr_avg_sentiment - prev_avg_sentiment
    if diff > 0.05:
        metrics["sentiment_trend"] = f"Up (+{diff:.2f})"
    elif diff < -0.05:
        metrics["sentiment_trend"] = f"Down ({diff:.2f})"
    else:
        metrics["sentiment_trend"] = "Stable"
        
    # Spike alerts (>30% WoW volume increase)
    prev_theme_map = {t.get("theme_name").lower(): t.get("review_count", 0) for t in prev_themes}
    for t in current_themes:
        name = t.get("theme_name", "")
        curr_count = t.get("review_count", 0)
        
        # Exact/Lower match
        prev_count = prev_theme_map.get(name.lower(), 0)
        
        # Only alert if there was some baseline and now it spiked
        if prev_count > 0:
            increase = (curr_count - prev_count) / prev_count
            if increase > config.SPIKE_ALERT_THRESHOLD:
                metrics["spike_alerts"].append({
                    "theme": name,
                    "increase_pct": increase * 100,
                    "prev_count": prev_count,
                    "curr_count": curr_count
                })
                
    return metrics


def call_gemini(themes, metrics):
    api_key = os.getenv(config.ENV_GEMINI_API_KEY)
    if not api_key:
        print(f"Error: {config.ENV_GEMINI_API_KEY} not set in environment.")
        sys.exit(1)
        
    genai.configure(api_key=api_key)
    
    # Sort themes by volume to get top N
    sorted_themes = sorted(themes, key=lambda x: x.get("review_count", 0), reverse=True)
    top_themes = sorted_themes[:config.REPORT_TOP_THEMES]
    
    # Format current state for prompt
    themes_str = json.dumps(top_themes, indent=2)
    spike_str = json.dumps(metrics.get("spike_alerts", []), indent=2)
    
    prompt = f"""
    You are a Senior Product Manager at Groww.
    Write a highly actionable Weekly Pulse Note based on the latest mobile app reviews.
    
    STRICT CONSTRAINTS:
    - Maximum {config.PULSE_MAX_WORDS} words.
    - Anonymize everything. No names, handles, or emails.
    - Output must be valid JSON matching this exact structure:
      {{
        "email_subject": "subject line (do not include date/week)",
        "email_highlight_summary": "Write exactly 3 lines using emoji traffic light format: 1. Top issue (e.g. 🔴 Top Issue: ...), 2. Watch item (e.g. 🟡 Watch Item: ...), 3. Recurring signal (e.g. 🟢 Clean Signal: ...)",
        "pdf_title": "Title for the PDF report",
        "sentiment_trend": "Short summary of the sentiment based on the data trend",
        "spikes": "Short text highlighting if there are spikes (or saying none)",
        "top_themes": [
            {{"name": "...", "volume": "...", "insight": "..."}} // Exactly {config.REPORT_TOP_THEMES} items
        ],
        "quotes": [
           "quote 1 text", "quote 2 text", "quote 3 text" // Exactly 3 anonymized quotes highlighting the core issues
        ],
        "action_ideas": [
           "idea 1", "idea 2", "idea 3" // Exactly 3 actionable product ideas based strictly on these themes
        ]
      }}
      
    DATA INPUT:
    Sentiment Trend Metric (WoW): {metrics.get('sentiment_trend')}
    Spike Alerts (>30% WoW volume increase): {spike_str}
    
    Top Themes (Volume, Sentiment, and Quotes):
    {themes_str}
    
    Generate the JSON payload now. Do not include markdown formatting like ```json.
    """
    
    # Ensure Gemini outputs JSON
    generation_config = {"response_mime_type": "application/json"}
    
    try:
        model = genai.GenerativeModel(config.GEMINI_MODEL, generation_config=generation_config)
    except Exception as e:
        # Fallback if older SDK version doesn't support response_mime_type
        print(f"Warning: {e}. Falling back to default Gemini generation config.")
        model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    print(f"Calling Gemini API ({config.GEMINI_MODEL})...")
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        
        # Clean markdown ticks if present
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        pulse_data = json.loads(raw_text.strip())
        return pulse_data
    except json.JSONDecodeError as j_err:
        print(f"Failed to parse Gemini output as JSON: {j_err}")
        print(f"Raw output: {raw_text}")
        return None
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None


def generate_pdf(pulse_data, date_str):
    os.makedirs(os.path.dirname(config.PDF_OUTPUT_PATH), exist_ok=True)
    
    doc = SimpleDocTemplate(
        config.PDF_OUTPUT_PATH, pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=30
    )
                            
    styles = getSampleStyleSheet()
    
    # Custom Groww-style PDF Theme
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=HexColor('#00D09C'),  # Groww Green
        spaceAfter=12
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#333333'),
        spaceBefore=14,
        spaceAfter=6
    )
    
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor('#444444'),
        spaceAfter=6
    )
    
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontSize=11,
        textColor=HexColor('#444444'),
        leftIndent=15,
        spaceAfter=4,
        bulletIndent=5
    )
    
    quote_style = ParagraphStyle(
        'Quote',
        parent=styles['Italic'],
        fontSize=10,
        textColor=HexColor('#666666'),
        leftIndent=20,
        rightIndent=20,
        spaceAfter=8
    )

    story = []
    
    # Header
    story.append(Paragraph(f"<b>{pulse_data.get('pdf_title', 'Groww Weekly Review Pulse')}</b>", title_style))
    story.append(Paragraph(f"<i>Week of {date_str}</i>", normal_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#EEEEEE'), spaceAfter=15))
    
    # 1. Overview (Sentiment & Spikes)
    story.append(Paragraph("<b>Overview</b>", heading_style))
    story.append(Paragraph(f"<b>Sentiment Trend:</b> {pulse_data.get('sentiment_trend', 'N/A')}", normal_style))
    story.append(Paragraph(f"<b>Spike Alerts:</b> {pulse_data.get('spikes', 'None')}", normal_style))
    story.append(Spacer(1, 10))
    
    # 2. Top Themes
    story.append(Paragraph("<b>Top Themes</b>", heading_style))
    for t in pulse_data.get("top_themes", []):
        theme_text = f"<b>{t.get('name', 'Unknown')}</b> (Volume: {t.get('volume', '0')}): {t.get('insight', '')}"
        story.append(Paragraph(theme_text, bullet_style))
    story.append(Spacer(1, 10))
        
    # 3. User Quotes
    story.append(Paragraph("<b>Voice of the User</b>", heading_style))
    for q in pulse_data.get("quotes", []):
        story.append(Paragraph(f"<i>\"{q}\"</i>", quote_style))
    story.append(Spacer(1, 10))
        
    # 4. Actionable Ideas
    story.append(Paragraph("<b>Product Opportunities</b>", heading_style))
    for idea in pulse_data.get("action_ideas", []):
        story.append(Paragraph(f"• {idea}", bullet_style))
        
    # Build the PDF
    try:
        doc.build(story)
        print(f"PDF generated successfully at: {config.PDF_OUTPUT_PATH}")
    except Exception as e:
        print(f"Failed to generate PDF: {e}")


def generate_charts(themes, metrics):
    """Generates base64 encoded png charts for email embedding."""
    charts = {}
    
    # 1. Theme Volumes Bar Chart
    if themes:
        # Sort by volume
        sorted_themes = sorted(themes, key=lambda x: x.get("review_count", 0), reverse=True)[:config.MAX_THEMES]
        names = [t.get("theme_name", "Unknown")[:20] + "..." if len(t.get("theme_name", ""))>20 else t.get("theme_name", "Unknown") for t in sorted_themes]
        volumes = [t.get("review_count", 0) for t in sorted_themes]
        
        plt.figure(figsize=(6, 4))
        plt.barh(names[::-1], volumes[::-1], color="#00D09C")
        plt.title("Top Themes by Volume")
        plt.xlabel("Number of Reviews")
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close()
        charts["themes_chart"] = base64.b64encode(buf.getvalue()).decode('utf-8')
        
    # 2. Sentiment Score Chart
    curr_sent = metrics.get('current_sentiment', 0.0)
    prev_sent = curr_sent # default if no previous
    
    if "sentiment_trend" in metrics and "Up" in metrics["sentiment_trend"]:
        try:
             diff = float(metrics["sentiment_trend"].split("+")[1].replace(")", ""))
             prev_sent = curr_sent - diff
        except: pass
    elif "sentiment_trend" in metrics and "Down" in metrics["sentiment_trend"]:
        try:
             diff = float(metrics["sentiment_trend"].split("(")[1].replace(")", ""))
             prev_sent = curr_sent - diff
        except: pass
        
    plt.figure(figsize=(5, 3))
    plt.bar(["Last Week", "This Week"], [prev_sent, curr_sent], color=["#CCCCCC", "#00D09C"])
    plt.title("Average Sentiment Score (0 to 1)")
    plt.ylim(0, 1.0)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    plt.close()
    charts["sentiment_chart"] = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return charts

def main():
    print("Starting Stage 4: pulse_generator.py")
    
    themes = load_themes()
    print(f"Loaded {len(themes)} themes from previous stage.")
    
    previous_snapshot = load_previous_snapshot()
    if previous_snapshot:
        print("Historical snapshot found! Computing Week-over-Week metrics (Sentiment & Spikes).")
    else:
        print("No prior snapshot found (Week 1). Using stable baseline metrics.")
        
    metrics = compute_metrics(themes, previous_snapshot)
    
    # Call Gemini to draft insights and the email text
    pulse_data = call_gemini(themes, metrics)
    if not pulse_data:
        print("CRITICAL: Failed to generate pulse data from Gemini.")
        sys.exit(1)
        
    # Inject current real-time metadata
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%B %d, %Y")
    
    pulse_data["generated_at"] = now_utc.isoformat()
    # Adding computed metrics for the deliver_and_commit snapshot to write later
    pulse_data["raw_metrics"] = metrics
    
    # Add charts and single-line summary statistics for the email module to use
    pulse_data["charts_base64"] = generate_charts(themes, metrics)
    pulse_data["email_stats"] = {
        "overall_sentiment": f"{metrics.get('current_sentiment', 0.0) * 100:.1f}%",
        "top_store": "Play Store" if config.PLAY_STORE_RATIO > config.APP_STORE_RATIO else "App Store",
        "reviews_analysed": config.LLM_INPUT_LIMIT
    }
    
    # Save the JSON pulse note
    os.makedirs(os.path.dirname(config.PULSE_NOTE_PATH), exist_ok=True)
    with open(config.PULSE_NOTE_PATH, "w", encoding="utf-8") as f:
        json.dump(pulse_data, f, indent=2, ensure_ascii=False)
    print(f"Pulse JSON saved to: {config.PULSE_NOTE_PATH}")
    
    # Generate the 1-page PDF
    generate_pdf(pulse_data, date_str)
    
    print("Stage 4 completed successfully.")


if __name__ == "__main__":
    main()
