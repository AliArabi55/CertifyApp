"""Simple JSON-file-based project storage (no database needed for a single-user local tool)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "projects"
DATA_DIR.mkdir(exist_ok=True)


def _project_dir(project_id: str) -> Path:
    return DATA_DIR / project_id


def create_project(name: str, mode: str = "certificates") -> dict:
    project_id = uuid.uuid4().hex[:10]
    pdir = _project_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "generated").mkdir(exist_ok=True)
    (pdir / "fonts").mkdir(exist_ok=True)
    (pdir / "email_images").mkdir(exist_ok=True)
    project = {
        "id": project_id,
        "name": name,
        "mode": mode,
        "background": None,
        "fields": [],
        "email_draft": {"subject": "", "html": ""},
    }
    save_project(project)
    return project


def save_project(project: dict) -> None:
    pdir = _project_dir(project["id"])
    with open(pdir / "project.json", "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)


def load_project(project_id: str) -> dict:
    path = _project_dir(project_id) / "project.json"
    if not path.exists():
        raise FileNotFoundError(project_id)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_projects() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    return [
        load_project(p.name)
        for p in DATA_DIR.iterdir()
        if p.is_dir() and (p / "project.json").exists()
    ]


def project_path(project_id: str, *parts: str) -> Path:
    return _project_dir(project_id).joinpath(*parts)
