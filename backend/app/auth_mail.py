"""Send account verification and password-reset messages from configured Gmail."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from urllib.parse import quote


def is_configured() -> bool:
    return bool(os.environ.get("CERTIFY_MAIL_FROM") and os.environ.get("CERTIFY_MAIL_APP_PASSWORD"))


def send_action_email(recipient: str, subject: str, action: str, token: str) -> None:
    sender = os.environ.get("CERTIFY_MAIL_FROM")
    password = os.environ.get("CERTIFY_MAIL_APP_PASSWORD")
    origin = os.environ.get("CERTIFY_PUBLIC_ORIGIN", "https://certify-ali-75931.azurewebsites.net").rstrip("/")
    if not sender or not password:
        raise RuntimeError("Account email delivery is not configured")
    link = f"{origin}/?{action}={quote(token)}"
    safe_link = escape(link, quote=True)
    message = MIMEMultipart("alternative")
    message["From"] = formataddr(("Certify", sender))
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(f"Open this link to continue: {link}\n\nIf you did not request this, ignore this email.", "plain", "utf-8"))
    message.attach(
        MIMEText(
            f'<p>Use the link below to continue. It expires soon.</p><p><a href="{safe_link}">Continue to Certify</a></p>'
            "<p>If you did not request this, you can ignore this email.</p>",
            "html",
            "utf-8",
        )
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ssl.create_default_context()) as smtp:
        smtp.login(sender, password.replace(" ", ""))
        smtp.sendmail(sender, [recipient], message.as_string())