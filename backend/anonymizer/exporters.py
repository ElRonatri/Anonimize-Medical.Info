"""Exportación del resultado anonimizado: Markdown, texto plano, Word (.docx) y JSON.

El JSON nunca incluye los valores originales detectados: sólo marcadores, categorías y
cantidades, para que el archivo exportado siga siendo anónimo.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from typing import Any

FORMATS = {
    "md": ("Markdown", ".md"),
    "txt": ("Texto", ".txt"),
    "docx": ("Word", ".docx"),
    "json": ("JSON", ".json"),
}

_PLACEHOLDER_RE = re.compile(r"(\[[A-Z][A-Z_]*\d*\])")
_BOLD_RE = re.compile(r"(\*\*[^*]+\*\*)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_PAGE_MARK_RE = re.compile(r"^\*([^*]+)\*$")
_ESCAPED_PIPE = "\u0000"


def export_bytes(fmt: str, text: str, meta: dict[str, Any] | None = None) -> bytes:
    meta = meta or {}
    if fmt == "docx":
        return to_docx(text, markdown=meta.get("format", "markdown") == "markdown")
    if fmt == "json":
        return to_json(text, meta).encode("utf-8")
    return text.encode("utf-8")


# --------------------------------------------------------------------------- JSON

def to_json(text: str, meta: dict[str, Any]) -> str:
    entities = [
        {"placeholder": e.get("placeholder"), "category": e.get("category"), "count": e.get("count", 0)}
        for e in meta.get("entities", [])
    ]
    payload = {
        "source_file": meta.get("name"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "Anonimize Medical",
        "language": meta.get("language"),
        "format": meta.get("format", "markdown"),
        "pages": meta.get("pages"),
        "ocr_pages": meta.get("ocr_pages", 0),
        "replacements": meta.get("replacements", sum(e["count"] for e in entities)),
        "entities": entities,
        "text": text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- Word

def to_docx(text: str, markdown: bool = True) -> bytes:
    from docx import Document
    from docx.enum.text import WD_BREAK
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    accent = RGBColor(0x0F, 0x76, 0x6E)

    def add_runs(paragraph: Any, content: str, bold: bool = False, italic: bool = False) -> None:
        parts = _BOLD_RE.split(content) if markdown else [content]
        for part in parts:
            if not part:
                continue
            is_bold = bold
            if markdown and part.startswith("**") and part.endswith("**") and len(part) > 4:
                part, is_bold = part[2:-2], True
            for chunk in _PLACEHOLDER_RE.split(part):
                if not chunk:
                    continue
                run = paragraph.add_run(chunk.replace(_ESCAPED_PIPE, "|"))
                run.bold = is_bold
                run.italic = italic
                if _PLACEHOLDER_RE.fullmatch(chunk):
                    run.bold = True
                    run.font.color.rgb = accent

    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            p = doc.add_paragraph()
            for n, line in enumerate(paragraph_lines):
                if n:
                    p.add_run().add_break()
                add_runs(p, line)
            paragraph_lines.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not markdown:
            if stripped.startswith("=====") and stripped.endswith("====="):
                flush_paragraph()
                if len(doc.paragraphs) > 1:
                    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
                add_runs(doc.add_paragraph(), stripped.strip("= "), italic=True)
            elif stripped:
                paragraph_lines.append(line.rstrip())
            else:
                flush_paragraph()
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped == "---":
            flush_paragraph()
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            i += 1
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)), 4)
            h = doc.add_heading(level=level)
            add_runs(h, heading.group(2))
            i += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                if not _TABLE_SEP_RE.match(row):
                    row = row.replace("\\|", _ESCAPED_PIPE).strip("|")
                    rows.append([c.strip() for c in row.split("|")])
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=width)
                table.style = "Table Grid"
                for r, cells in enumerate(rows):
                    for c in range(width):
                        cell = table.cell(r, c)
                        add_runs(cell.paragraphs[0], cells[c] if c < len(cells) else "", bold=(r == 0))
                doc.add_paragraph()
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            flush_paragraph()
            add_runs(doc.add_paragraph(style="List Bullet"), bullet.group(1))
            i += 1
            continue

        numbered = _NUMBERED_RE.match(line)
        if numbered:
            flush_paragraph()
            add_runs(doc.add_paragraph(style="List Number"), numbered.group(1))
            i += 1
            continue

        page_mark = _PAGE_MARK_RE.match(stripped)
        if page_mark:
            flush_paragraph()
            add_runs(doc.add_paragraph(), page_mark.group(1), italic=True)
            i += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            add_runs(doc.add_paragraph(), stripped.lstrip("> "), italic=True)
            i += 1
            continue

        paragraph_lines.append(stripped)
        i += 1

    flush_paragraph()
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
