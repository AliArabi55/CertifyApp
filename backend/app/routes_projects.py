"""Project CRUD, certificate designer, template generation, and bulk certificate rendering."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

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
async def upload_background(project_id: str, file: UploadFile = File(...)):
    project = storage.load_project(project_id)
    ext = Path(file.filename).suffix or ".png"
    dest = storage.project_path(project_id, f"background{ext}")
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    project["background"] = dest.name
    storage.save_project(project)
    return project


@router.put("/{project_id}/fields")
def save_fields(project_id: str, fields: list[dict] = Body(...)):
    project = storage.load_project(project_id)
    project["fields"] = fields
    storage.save_project(project)
    return project


@router.post("/{project_id}/fonts")
async def upload_font(project_id: str, file: UploadFile = File(...)):
    dest = storage.project_path(project_id, "fonts", file.filename)
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"filename": file.filename}


@router.get("/{project_id}/template.xlsx")
def download_template(project_id: str):
    project = storage.load_project(project_id)
    field_names = [f["name"] for f in project["fields"]]
    draft = project.get("email_draft", {})
    extra = email_utils.detect_variables(draft.get("html", "")) + email_utils.detect_variables(
        draft.get("subject", "")
    )
    columns = ["Email"] + list(dict.fromkeys(field_names + extra))
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
async def generate(project_id: str, file: UploadFile = File(...)):
    project = storage.load_project(project_id)
    mode = project.get("mode", "certificates")
    xlsx_path = storage.project_path(project_id, "data.xlsx")
    with open(xlsx_path, "wb") as out:
        shutil.copyfileobj(file.file, out)
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
    for row in rows:
        email = row.get("Email")
        if not email:
            continue
        safe_name = "".join(c if c.isalnum() else "_" for c in str(row.get("Name", email)))
        out_path = gen_dir / f"Certificate_{safe_name}.pdf"
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
