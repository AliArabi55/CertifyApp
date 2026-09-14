"""Email draft storage, variable detection, per-recipient preview, and inline image uploads."""
from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from . import email_utils, storage

router = APIRouter(prefix="/api/projects", tags=["email"])


@router.put("/{project_id}/email-draft")
def save_draft(project_id: str, draft: dict = Body(...)):
    project = storage.load_project(project_id)
    if not all(isinstance(draft.get(key, ""), str) for key in ("subject", "html")):
        raise HTTPException(400, "Subject and HTML must be text")
    if any(character in draft.get("subject", "") for character in "\r\n"):
        raise HTTPException(400, "Subject must be a single line")
    project["email_draft"] = {"subject": draft.get("subject", ""), "html": draft.get("html", "")}
    storage.save_project(project)
    variables = sorted(
        set(
            email_utils.detect_variables(draft.get("subject", ""))
            + email_utils.detect_variables(draft.get("html", ""))
        )
    )
    return {"project": project, "variables": variables}


@router.post("/{project_id}/email-preview")
def preview_email(project_id: str, row: dict = Body(...)):
    project = storage.load_project(project_id)
    draft = project.get("email_draft", {})
    html = email_utils.render_html(draft.get("html", ""), row)
    html = email_utils.inline_cid_to_preview_urls(html, project_id)
    return {
        "subject": email_utils.render_template(draft.get("subject", ""), row),
        "html": html,
    }


@router.post("/{project_id}/email-images")
async def upload_email_image(project_id: str, file: UploadFile = File(...)):
    storage.load_project(project_id)
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Images must be 10 MB or smaller")
    try:
        with Image.open(io.BytesIO(content)) as image:
            extension = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}.get(image.format)
            image.verify()
        if not extension:
            raise ValueError("Unsupported image format")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "Upload a valid PNG, JPEG, GIF or WebP image") from exc
    dest_dir = storage.project_path(project_id, "email_images")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"image_{uuid.uuid4().hex}.{extension}"
    dest.write_bytes(content)
    return {"filename": dest.name, "cid": email_utils.safe_cid(dest.stem)}


@router.get("/{project_id}/email-images/by-cid/{cid}")
def get_email_image_by_cid(project_id: str, cid: str):
    images_dir = storage.project_path(project_id, "email_images")
    if images_dir.exists():
        for f in images_dir.iterdir():
            if f.is_file() and email_utils.safe_cid(f.stem) == cid:
                return FileResponse(f)
    raise HTTPException(404)
