"""Email draft storage, variable detection, per-recipient preview, and inline image uploads."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import email_utils, storage

router = APIRouter(prefix="/api/projects", tags=["email"])


@router.put("/{project_id}/email-draft")
def save_draft(project_id: str, draft: dict = Body(...)):
    project = storage.load_project(project_id)
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
    html = email_utils.render_template(draft.get("html", ""), row)
    html = email_utils.inline_cid_to_preview_urls(html, project_id)
    return {
        "subject": email_utils.render_template(draft.get("subject", ""), row),
        "html": html,
    }


@router.post("/{project_id}/email-images")
async def upload_email_image(project_id: str, file: UploadFile = File(...)):
    dest_dir = storage.project_path(project_id, "email_images")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"filename": dest.name, "cid": email_utils.safe_cid(dest.stem)}


@router.get("/{project_id}/email-images/by-cid/{cid}")
def get_email_image_by_cid(project_id: str, cid: str):
    images_dir = storage.project_path(project_id, "email_images")
    if images_dir.exists():
        for f in images_dir.iterdir():
            if f.is_file() and email_utils.safe_cid(f.stem) == cid:
                return FileResponse(f)
    raise HTTPException(404)
