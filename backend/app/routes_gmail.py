"""Gmail App Password connection (no OAuth, no Google Cloud project) and the test/send-all flow."""
from __future__ import annotations

import asyncio
import csv
import smtplib
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Body, HTTPException

from . import email_utils, gmail_smtp, storage

router = APIRouter(tags=["gmail"])
_send_locks: dict[str, Lock] = {}


def _collect_inline_images(project_id: str) -> dict[str, Path]:
    images_dir = storage.project_path(project_id, "email_images")
    if not images_dir.exists():
        return {}
    return {email_utils.safe_cid(f.stem): f for f in images_dir.iterdir() if f.is_file()}


@router.post("/api/gmail/connect")
async def gmail_connect(email: str = Body(embed=True), app_password: str = Body(embed=True)):
    try:
        connected_email = await asyncio.to_thread(gmail_smtp.connect, email, app_password)
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            400,
            "Invalid email or App Password. Make sure 2-Step Verification is enabled on this "
            "Google account and you're using a 16-character App Password, not your regular password.",
        )
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"connected": True, "email": connected_email}


@router.post("/api/gmail/disconnect")
def gmail_disconnect():
    gmail_smtp.disconnect()
    return {"connected": False}


@router.get("/api/gmail/status")
def gmail_status():
    return {"connected": gmail_smtp.is_connected(), "email": gmail_smtp.get_connected_email()}


@router.post("/api/projects/{project_id}/send-test")
async def send_test(project_id: str, to: str = Body(embed=True), row: dict = Body(embed=True)):
    project = storage.load_project(project_id)
    draft = project.get("email_draft", {})
    subject = "[TEST] " + email_utils.render_template(draft.get("subject", ""), row)
    html = email_utils.render_html(draft.get("html", ""), row)
    cert_file = row.get("_certificate_file")
    attachment = storage.project_path(project_id, "generated", cert_file) if cert_file else None
    try:
        await asyncio.to_thread(
            gmail_smtp.send_email,
            project.get("name", "Certify"),
            to,
            subject,
            html,
            attachment,
            _collect_inline_images(project_id),
        )
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"sent": True}


@router.post("/api/projects/{project_id}/send-all")
async def send_all(project_id: str, rows: list[dict] = Body(embed=True), force: bool = Body(False, embed=True)):
    storage.load_project(project_id)
    lock = _send_locks.setdefault(project_id, Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A send operation is already running for this project")
    try:
        return await _send_all(project_id, rows, force)
    finally:
        lock.release()


async def _send_all(project_id: str, rows: list[dict], force: bool):
    project = storage.load_project(project_id)
    draft = project.get("email_draft", {})
    log_path = storage.project_path(project_id, "send_log.csv")
    inline_images = _collect_inline_images(project_id)

    already_sent: set[str] = set()
    if log_path.exists() and not force:
        with open(log_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("status") == "sent":
                    already_sent.add(r["email"].strip().casefold())

    sent_count = 0
    results = []
    for row in rows:
        email = str(row.get("Email") or "").strip()
        if not email:
            results.append({"email": "", "status": "skipped: missing email"})
            continue
        if email.casefold() in already_sent:
            results.append({"email": email, "status": "skipped: already sent"})
            continue
        subject = email_utils.render_template(draft.get("subject", ""), row)
        html = email_utils.render_html(draft.get("html", ""), row)
        cert_file = row.get("_certificate_file")
        attachment = storage.project_path(project_id, "generated", cert_file) if cert_file else None
        try:
            await asyncio.to_thread(
                gmail_smtp.send_email,
                project.get("name", "Certify"),
                email,
                subject,
                html,
                attachment,
                inline_images,
            )
            status = "sent"
            sent_count += 1
            already_sent.add(email.casefold())
        except Exception as e:
            status = f"error: {e}"
        results.append({"email": email, "status": status})

        is_new = not log_path.exists()
        with open(log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "email", "status"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), email, status])
        await asyncio.sleep(2)  # basic rate limiting between sends

    return {"sent": sent_count, "results": results}
