"""
output/email_sender.py — Send the digest by email via Gmail SMTP.

Requires two GitHub Actions secrets:
  - GMAIL_USER: your sending Gmail address
  - GMAIL_APP_PASSWORD: a Gmail App Password (not your account password)
    Generate at: https://myaccount.google.com/apppasswords

The email is sent as HTML (converted from markdown) with a plain-text fallback.
"""

import logging
import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EMAIL_RECIPIENT, EMAIL_SUBJECT_PREFIX

logger = logging.getLogger(__name__)


def send_digest(markdown_content: str, article_count: int) -> bool:
    """
    Send the markdown digest as an HTML email.
    Returns True on success, False on failure.
    """
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        logger.error(
            "Email not sent: GMAIL_USER or GMAIL_APP_PASSWORD not set in environment"
        )
        return False

    run_date = datetime.now(timezone.utc).strftime("%d %B %Y")
    subject = f"{EMAIL_SUBJECT_PREFIX} — {run_date} ({article_count} stories)"

    html_body = _markdown_to_html(markdown_content)
    plain_body = markdown_content  # Plain-text fallback

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = EMAIL_RECIPIENT

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, EMAIL_RECIPIENT, msg.as_string())
        logger.info(f"Digest emailed to {EMAIL_RECIPIENT}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email: {exc}")
        return False


def _markdown_to_html(md: str) -> str:
    """
    Minimal markdown-to-HTML conversion sufficient for the digest format.
    Handles: h1/h2/h3, bold, links, blockquotes, hr, italic, paragraphs.
    For a richer conversion, replace with the `markdown` package if desired.
    """
    lines = md.split("\n")
    html_lines = []
    in_blockquote = False

    for line in lines:
        # Headings
        if line.startswith("### "):
            content = _inline(line[4:])
            html_lines.append(f'<h3 style="margin-bottom:4px;color:#1a1a2e;">{content}</h3>')
        elif line.startswith("## "):
            content = _inline(line[3:])
            html_lines.append(
                f'<h2 style="margin-top:24px;margin-bottom:8px;color:#16213e;'
                f'border-bottom:2px solid #0f3460;padding-bottom:4px;">{content}</h2>'
            )
        elif line.startswith("# "):
            content = _inline(line[2:])
            html_lines.append(
                f'<h1 style="color:#0f3460;font-size:24px;margin-bottom:4px;">{content}</h1>'
            )
        # Blockquote
        elif line.startswith("> "):
            content = _inline(line[2:])
            html_lines.append(
                f'<blockquote style="border-left:3px solid #0f3460;margin:8px 0;'
                f'padding:4px 12px;color:#444;font-style:italic;">{content}</blockquote>'
            )
        # HR
        elif line.strip() == "---":
            html_lines.append('<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;">')
        # Empty line
        elif line.strip() == "":
            html_lines.append("")
        # Regular paragraph
        else:
            content = _inline(line)
            html_lines.append(f'<p style="margin:4px 0;">{content}</p>')

    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:700px;margin:0 auto;padding:20px;color:#1a1a1a;line-height:1.6;">
{body}
<br>
<p style="font-size:12px;color:#999;border-top:1px solid #eee;padding-top:12px;">
This digest is generated automatically. To stop receiving it, remove your address from config.py.
</p>
</body>
</html>"""


def _inline(text: str) -> str:
    """Convert inline markdown (bold, links, italic) to HTML."""
    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color:#0f3460;">\1</a>',
        text,
    )
    # Bold: **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic: *text*
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    return text
