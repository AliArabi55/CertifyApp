"""Excel template generation and reading for the recipients sheet."""
from __future__ import annotations

from pathlib import Path

import openpyxl


def generate_template(columns: list[str], out_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(columns)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def read_rows(xlsx_path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = []
    for values in ws.iter_rows(min_row=2, values_only=True):
        if values[0] is None:
            continue
        rows.append(dict(zip(header, values)))
    return rows
