"""Gmail sending via SMTP + an App Password — no Google Cloud project or OAuth needed.

Credentials are saved locally in config/.env (gitignored). This keeps the tool
"plug & play": anyone can generate their own App Password in ~1 minute (see README)
instead of creating a Google Cloud OAuth client.
"""
from __future__ import annotations

import smtplib
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
CONFIG_DIR.mkdir(exist_ok=True)
ENV_PATH = CONFIG_DIR / ".env"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _read_env() -> dict:
    values: dict = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _write_env(values: dict) -> None:
    lines = [f"{k}={v}" for k, v in values.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_connected() -> bool:
    env = _read_env()
    return bool(env.get("GMAIL_ADDRESS") and env.get("GMAIL_APP_PASSWORD"))


def get_connected_email() -> Optional[str]:
    return _read_env().get("GMAIL_ADDRESS")


def connect(email: str, app_password: str) -> str:
    """Validates the App Password with a real login, then saves it locally."""
    password = app_password.replace(" ", "")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(email, password)
    _write_env({"GMAIL_ADDRESS": email, "GMAIL_APP_PASSWORD": password})
    return email


def disconnect() -> None:
    if ENV_PATH.exists():
        ENV_PATH.unlink()


def _subtype_for(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return "jpeg" if ext == "jpg" else ext


def send_email(
    sender_name: str,
    to_email: str,
    subject: str,
    html_body: str,
    attachment_path: Optional[Path] = None,
    inline_images: Optional[dict] = None,
) -> None:
    env = _read_env()
    sender_email = env.get("GMAIL_ADDRESS")
    app_password = env.get("GMAIL_APP_PASSWORD")
    if not sender_email or not app_password:
        raise RuntimeError("Gmail is not connected yet. Enter your address and App Password first.")

    msg = MIMEMultipart("mixed")
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html"))
    for cid, img_path in (inline_images or {}).items():
        with open(img_path, "rb") as f:
            img = MIMEImage(f.read(), _subtype=_subtype_for(Path(img_path)))
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=Path(img_path).name)
        related.attach(img)
    msg.attach(related)

    if attachment_path:
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
        part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
        msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(sender_email, app_password)
        smtp.sendmail(sender_email, [to_email], msg.as_string())
