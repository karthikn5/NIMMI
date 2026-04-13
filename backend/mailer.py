import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

async def send_reset_email(email: str, token: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    dashboard_url = os.getenv("DASHBOARD_URL", "https://nimmai.in").rstrip("/")
    
    if not all([smtp_host, smtp_user, smtp_pass]):
        logger.warning(f"SMTP not configured. Token for {email}: {token}")
        # In development/missing config, we just log it
        return False

    msg = EmailMessage()
    msg.set_content(f"""
Hi,

You requested a password reset for your Nimmi AI account.
Click the link below to set a new password:

{dashboard_url}/auth/reset-password?token={token}

This link will expire in 1 hour. If you did not request this, please ignore this email.

Best,
Nimmi AI Team
""")

    msg['Subject'] = "Reset your Nimmi AI Password"
    msg['From'] = smtp_user
    msg['To'] = email

    try:
        # Use synchronous smtplib in a thread pool if needed, but for now simple sync call
        # Since we are using this in a background task or small scale, it's fine.
        with smtplib.SMTP(smtp_host, int(smtp_port)) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
