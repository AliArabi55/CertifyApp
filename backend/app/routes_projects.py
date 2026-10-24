"""Project CRUD, certificate designer, template generation, and bulk certificate rendering."""
from __future__ import annotations

import uuid
import io
import math
import re
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageFont, ImageOps, UnidentifiedImageError

from . import cert_render, email_utils, excel_utils, storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects():
    return storage.list_projects()


@router.post("")
def create_project(name: str = Form(...), mode: str = Form("certificates")):
    return storage.create_project(name, mode)


@router.get("/{project_id}")
def get_project(project_id: str):
    try:
        return storage.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")


@router.post("/{project_id}/background")
def upload_background(project_id: str, file: UploadFile = File(...)):
    project = storage.load_project(project_id)
    content = file.file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Background images must be 20 MB or smaller")
    dest = storage.project_path(project_id, "background.png")
    try:
        with Image.open(io.BytesIO(content)) as image:
            ImageOps.exif_transpose(image).convert("RGB").save(dest, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "Upload a valid background image") from exc
    project["background"] = dest.name
    storage.save_project(project)
    return project


@router.put("/{project_id}/fields")
def save_fields(project_id: str, fields: list[dict] = Body(...)):
    project = storage.load_project(project_id)
    names = set()
    if len(fields) > 100:
        raise HTTPException(400, "A certificate can contain at most 100 fields")
    for field in fields:
        name = field.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]*", name) or name in names:
            raise HTTPException(400, "Field names must be unique and contain only letters, numbers and underscores")
        names.add(name)
        for key in ("x", "y", "font_size"):
            value = field.get(key, 40 if key == "font_size" else None)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise HTTPException(400, f"Invalid field {key}")
        if not 1 <= field.get("font_size", 40) <= 2000:
            raise HTTPException(400, "Font size must be between 1 and 2000")
        color = field.get("color", "#000000")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise HTTPException(400, "Color must be a six-digit hex color")
        if any(not isinstance(field.get(key, False), bool) for key in ("bold", "italic")):
            raise HTTPException(400, "Bold and italic must be boolean values")
        anchor = field.get("anchor", "mm")
        if not isinstance(anchor, str) or not re.fullmatch(r"[lmr][atmsbd]", anchor):
            raise HTTPException(400, "Invalid text anchor")
        storage.project_path(project_id, "fonts", field.get("font", "arial.ttf"))
    project["fields"] = fields
    storage.save_project(project)
    return project


@router.post("/{project_id}/fonts")
def upload_font(project_id: str, file: UploadFile = File(...)):
    storage.load_project(project_id)
    dest = storage.project_path(project_id, "fonts", file.filename)
    if dest.suffix.lower() != ".ttf":
        raise HTTPException(400, "Upload a .ttf font")
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Fonts must be 10 MB or smaller")
    try:
        ImageFont.truetype(io.BytesIO(content), 20)
    except OSError as exc:
        raise HTTPException(400, "Upload a valid TrueType font") from exc
    dest.write_bytes(content)
    return {"filename": dest.name}


@router.get("/{project_id}/fonts/{filename}")
def font_asset(project_id: str, filename: str):
    path = storage.project_path(project_id, "fonts", filename)
    if path.suffix.lower() != ".ttf" or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="font/ttf")


@router.get("/{project_id}/template.xlsx")
def download_template(project_id: str):
    project = storage.load_project(project_id)
    field_names = [f["name"] for f in project["fields"]]
    draft = project.get("email_draft", {})
    extra = email_utils.detect_variables(draft.get("html", "")) + email_utils.detect_variables(
        draft.get("subject", "")
    )
    columns = list(dict.fromkeys(["Email", "Name"] + field_names + extra))
    out_path = storage.project_path(project_id, "template.xlsx")
    excel_utils.generate_template(columns, out_path)
    return FileResponse(out_path, filename=f"{project['name']}_template.xlsx")


@router.post("/{project_id}/preview")
def preview(project_id: str, row: dict | None = Body(None)):
    project = storage.load_project(project_id)
    if not project.get("background"):
        raise HTTPException(400, "Upload a background image first")
    sample_row = row or {f["name"]: f["name"] for f in project["fields"]}
    bg_path = storage.project_path(project_id, project["background"])
    fonts_dir = storage.project_path(project_id, "fonts")
    out_path = storage.project_path(project_id, "preview.png")
    cert_render.render_certificate(bg_path, project["fields"], sample_row, fonts_dir, out_path)
    return FileResponse(out_path, filename="preview.png")


@router.post("/{project_id}/generate")
def generate(project_id: str, file: UploadFile = File(...)):
    project = storage.load_project(project_id)
    mode = project.get("mode", "certificates")
    content = file.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Workbooks must be 10 MB or smaller")
    xlsx_path = storage.project_path(project_id, "data.xlsx")
    xlsx_path.write_bytes(content)
    rows = excel_utils.read_rows(xlsx_path)

    if mode == "emails_only":
        results = [row for row in rows if row.get("Email")]
        return {"count": len(results), "rows": results}

    if not project.get("background"):
        raise HTTPException(400, "Upload a background image first")
    bg_path = storage.project_path(project_id, project["background"])
    fonts_dir = storage.project_path(project_id, "fonts")
    gen_dir = storage.project_path(project_id, "generated")

    results = []
    batch_id = uuid.uuid4().hex[:10]
    for index, row in enumerate(rows, start=1):
        email = row.get("Email")
        if not email:
            continue
        safe_name = "".join(c if c.isalnum() else "_" for c in str(row.get("Name", email)))
        out_path = gen_dir / f"Certificate_{safe_name[:80]}_{batch_id}_{index}.pdf"
        cert_render.render_certificate(bg_path, project["fields"], row, fonts_dir, out_path)
        row["_certificate_file"] = out_path.name
        results.append(row)
    return {"count": len(results), "rows": results}


@router.get("/{project_id}/asset/{filename}")
def project_asset(project_id: str, filename: str):
    path = storage.project_path(project_id, filename)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@router.get("/{project_id}/generated/{filename}")
def generated_asset(project_id: str, filename: str):
    path = storage.project_path(project_id, "generated", filename)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
