"""Excel template generation and reading for the recipients sheet."""
from __future__ import annotations

from pathlib import Path
import re

import openpyxl


def generate_template(columns: list[str], out_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def read_rows(xlsx_path: Path) -> list[dict]:
    try:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("Upload a valid .xlsx workbook") from exc
    try:
        ws = wb.active
        header = [str(cell.value or "").strip() for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        header = ["Email" if name.casefold() == "email" else name for name in header]
        names = [name for name in header if name]
        if "Email" not in names:
            raise ValueError("The workbook must have an Email column")
        if len(set(names)) != len(names) or any(name.startswith("_") for name in names):
            raise ValueError("Column names must be unique and cannot start with an underscore")
        rows = []
        for number, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if all(value is None or value == "" for value in values):
                continue
            row = {name: value if value is not None else "" for name, value in zip(header, values) if name}
            email = str(row.get("Email") or "").strip()
            if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
                raise ValueError(f"Row {number}: enter a valid Email address")
            row["Email"] = email
            rows.append(row)
        if not rows:
            raise ValueError("The workbook contains no recipients")
        return rows
    finally:
        wb.close()
