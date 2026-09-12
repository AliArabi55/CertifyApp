"""Renders a certificate for one recipient by drawing text fields onto a background image."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WINDOWS_FONTS_DIR = Path(r"C:\Windows\Fonts")


def resolve_font(font_name: str, size: int, fonts_dir: Path) -> ImageFont.FreeTypeFont:
    """Looks for a custom uploaded font first, then falls back to Windows system fonts."""
    candidates = [fonts_dir / font_name, WINDOWS_FONTS_DIR / font_name]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    try:
        return ImageFont.truetype(font_name, size)
    except OSError:
        return ImageFont.load_default()


def render_certificate(
    background_path: Path,
    fields: list[dict],
    row: dict,
    fonts_dir: Path,
    out_path: Path,
) -> Path:
    img = Image.open(background_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    for field in fields:
        text = str(row.get(field["name"], ""))
        if not text:
            continue
        font = resolve_font(field.get("font", "arial.ttf"), int(field.get("font_size", 40)), fonts_dir)
        draw.text(
            (field["x"], field["y"]),
            text,
            fill=field.get("color", "#000000"),
            font=font,
            anchor=field.get("anchor", "mm"),
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
