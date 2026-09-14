"""Renders a certificate for one recipient by drawing text fields onto a background image."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WINDOWS_FONTS_DIR = Path(r"C:\Windows\Fonts")
FONT_VARIANTS = (
    ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
)


def styled_font(font_name: str, bold: bool, italic: bool) -> str:
    for variants in FONT_VARIANTS:
        if font_name.lower() in variants:
            current = variants.index(font_name.lower())
            return variants[current | int(bold) | (int(italic) << 1)]
    return font_name


def resolve_font(font_name: str, size: int, fonts_dir: Path) -> ImageFont.FreeTypeFont:
    """Looks for a custom uploaded font first, then falls back to Windows system fonts."""
    if any(character in font_name for character in "/\\:"):
        raise ValueError("Font must be a filename")
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
        value = row.get(field["name"])
        text = "" if value is None else str(value)
        if not text:
            continue
        font_name = styled_font(field.get("font", "arial.ttf"), field.get("bold", False), field.get("italic", False))
        font = resolve_font(font_name, int(field.get("font_size", 40)), fonts_dir)
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
