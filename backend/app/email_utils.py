"""{{Variable}} placeholder detection and rendering, shared by certificates and email drafts."""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
CID_SRC_PATTERN = re.compile(r"cid:([a-zA-Z0-9_]+)")


def detect_variables(text: str) -> list[str]:
    seen: list[str] = []
    for m in VAR_PATTERN.finditer(text or ""):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def render_template(text: str, row: dict) -> str:
    return VAR_PATTERN.sub(lambda m: "" if row.get(m.group(1)) is None else str(row[m.group(1)]), text or "")


def render_html(text: str, row: dict) -> str:
    return render_template(text, {key: escape(str(value), quote=True) if value is not None else "" for key, value in row.items()})


class _PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.parts.append(f" ({value}) ")


def plain_text(html: str) -> str:
    parser = _PlainTextParser()
    parser.feed(html)
    return "".join(parser.parts).strip()


def safe_cid(name: str) -> str:
    """Turns a filename stem into a stable, email-safe Content-ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()


def inline_cid_to_preview_urls(html: str, project_id: str) -> str:
    """Rewrites cid: image sources to browser-loadable URLs, for in-app preview only."""
    return CID_SRC_PATTERN.sub(
        lambda m: f"/api/projects/{project_id}/email-images/by-cid/{m.group(1)}", html or ""
    )
