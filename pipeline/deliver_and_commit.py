import os
import sys
import json
import smtplib
import subprocess
from email.message import EmailMessage
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def send_email(pulse_data, is_fallback=False):
    """Sends the pulse note via Gmail SMTP with PDF attached."""
    
    sender = os.getenv(config.ENV_GMAIL_ADDRESS)
    password = os.getenv(config.ENV_GMAIL_APP_PASSWORD)
    recipient = os.getenv(config.ENV_RECIPIENT_EMAIL)
    
    if not all([sender, password, recipient]):
        print(f"Error: Missing email credentials in environment variables.")
        print(f"Check {config.ENV_GMAIL_ADDRESS}, {config.ENV_GMAIL_APP_PASSWORD}, and {config.ENV_RECIPIENT_EMAIL}")
        return False

    # Construct Date/Week strings
    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%B %d, %Y")
    
    # Base Subject
    subject = pulse_data.get("email_subject", f"{config.EMAIL_SUBJECT_PREFIX} {date_str}")
    
    # Add Warning Flag if pipeline failed and we fell back to last week's data
    if is_fallback:
        subject = f"⚠️ [Data Pending] {subject}"
        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    # Construct Body
    body_intro = pulse_data.get("email_body_draft", "Please find the Weekly Pulse Note attached.")
    
    body = f"""Hi Team,

{body_intro}

{"*Note: This report contains data pending from previous weeks due to a temporary data fetch delay.*" if is_fallback else ""}

Please find the detailed 1-page report attached as a PDF.

Best,
Automated Pulse Engine
"""
    msg.set_content(body)

    # Attach PDF
    if os.path.exists(config.PDF_OUTPUT_PATH):
        with open(config.PDF_OUTPUT_PATH, 'rb') as f:
            pdf_data = f.read()
        msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=os.path.basename(config.PDF_OUTPUT_PATH))
    else:
        print(f"Warning: PDF not found at {config.PDF_OUTPUT_PATH}. Sending email without attachment.")

    print(f"Connecting to {config.SMTP_HOST}:{config.SMTP_PORT}...")
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.set_debuglevel(0) # set to 1 for raw SMTP output if debugging needed
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            print(f"Email successfully sent to {recipient}")
            return True
    except smtplib.SMTPAuthenticationError:
        print("SMTP Auth Error: The Gmail App Password is incorrect or the account has blocked the login attempt.")
    except Exception as e:
        print(f"Failed to send email: {e}")
    return False

def commit_snapshot():
    """Commits the current themes to the GitHub repository to serve as the baseline for next week."""
    
    # We only commit if we are inside GitHub Actions
    if not os.getenv("GITHUB_ACTIONS"):
        print("Not running in GitHub Actions: Skipping snapshot commit step to avoid dirtying local directory.")
        return True
        
    if not os.path.exists(config.THEMES_PATH):
        print(f"No {config.THEMES_PATH} found to snapshot.")
        return False
        
    now_utc = datetime.now(timezone.utc)
    # Week format YYYY-WW (e.g., 2026-11)
    year, week, _ = now_utc.isocalendar()
    snapshot_filename = f"{year}-W{week:02}.json"
    snapshot_path = os.path.join(config.SNAPSHOT_DIR, snapshot_filename)
    
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    
    try:
        # Load themes, merge with metrics if available
        with open(config.THEMES_PATH, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
            
        if os.path.exists(config.PULSE_NOTE_PATH):
            with open(config.PULSE_NOTE_PATH, "r", encoding="utf-8") as f:
                pulse_data = json.load(f)
                if "raw_metrics" in pulse_data:
                    snapshot_data["metrics"] = pulse_data["raw_metrics"]
                    
        # Write snapshot
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)
            
        print(f"Created snapshot: {snapshot_path}")
        
        # Git config
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        
        # Git add & commit
        subprocess.run(["git", "add", snapshot_path], check=True)
        
        # Check if there's anything to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if snapshot_path in status.stdout or snapshot_filename in status.stdout:
            subprocess.run(["git", "commit", "-m", f"chore(snapshots): save week {year}-W{week:02} pulse snapshot [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Successfully committed and pushed snapshot to GitHub.")
        else:
            print("Snapshot unchanged or already committed.")
            
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git execution failed: {e}")
        return False
    except Exception as e:
        print(f"Failed to create/commit snapshot: {e}")
        return False


def main():
    print("Starting Stage 5: deliver_and_commit.py")
    
    # 1. Load Pulse Note Data
    if not os.path.exists(config.PULSE_NOTE_PATH):
        print(f"Error: {config.PULSE_NOTE_PATH} not found. Ensure Stage 4 succeeded.")
        sys.exit(1)
        
    with open(config.PULSE_NOTE_PATH, "r", encoding="utf-8") as f:
        pulse_data = json.load(f)
        
    # Check if themes was a fallback
    is_fallback = False
    if os.path.exists(config.THEMES_PATH):
         with open(config.THEMES_PATH, "r", encoding="utf-8") as f:
            themes_data = json.load(f)
            is_fallback = themes_data.get("is_fallback", False)
            
    # 2. Email Delivery
    email_success = send_email(pulse_data, is_fallback)
    
    # 3. Snapshot Commit (only if not fallback, so we don't overwrite with stale data)
    if not is_fallback:
        commit_success = commit_snapshot()
    else:
        print("Skipping snapshot commit because current pipeline ran in Fallback mode.")
        commit_success = True
        
    if email_success and commit_success:
        print("Stage 5 completed successfully.")
    else:
        print("Stage 5 completed with warnings/errors.")
        sys.exit(1 if not email_success else 0)

if __name__ == "__main__":
    main()
