"""Convierte el documento (ya anonimizado pieza a pieza) en Markdown o texto plano."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

from .document import Block, Document, Page
from .lang import NO_TEXT_PAGE, PAGE_LABEL
from .rules import NEXT_LABEL_RE

Redact = Callable[[str], str]

BULLET_RE = re.compile(r"^\s*[-•·*–▪●◦■□➢►]\s+")
NUMBERED_RE = re.compile(r"^\s*\d{1,2}[.)]\s+")
KV_RE = re.compile(r"^([^:|]{1,45}?)\s*:\s*(.+)$")
TIME_LIKE_RE = re.compile(r"\d\s*$")
WIDE_GAP_RE = re.compile(r"\s{3,}")
_DIGITS_RE = re.compile(r"\d+")


# --------------------------------------------------------------------------- encabezados/pies repetidos

def _signature(text: str) -> str:
    return _DIGITS_RE.sub("#", " ".join(text.lower().split()))


def strip_repeated_lines(doc: Document, window: int = 4) -> Document:
    """Elimina encabezados y pies de página que se repiten en la mayoría de las páginas.

    Conserva la primera aparición (suele ser el membrete del documento).
    """
    pages = [p for p in doc.pages if not p.empty]
    if len(pages) < 2:
        return doc

    def edge_lines(page: Page) -> list[Block]:
        lines = [b for b in page.blocks if b.kind == "line" and b.text.strip()]
        return lines[:window] + lines[-window:]

    counts: Counter[str] = Counter()
    variants: dict[str, set[str]] = {}
    for page in pages:
        for block in edge_lines(page):
            variants.setdefault(_signature(block.text), set()).add(" ".join(block.text.split()))
        counts.update({_signature(b.text) for b in edge_lines(page)})
    threshold = max(2, int(len(pages) * 0.6 + 0.5))
    repeated = {sig for sig, n in counts.items() if n >= threshold and sig}
    if not repeated:
        return doc

    seen: set[str] = set()
    new_pages = []
    for page in doc.pages:
        edge_ids = {id(b) for b in edge_lines(page)}
        blocks = []
        for block in page.blocks:
            if id(block) in edge_ids:
                sig = _signature(block.text)
                if sig in repeated:
                    # Texto idéntico en cada página (membrete): se conserva la primera vez.
                    # Texto que sólo cambia en números (p. ej. "Página 3"): se elimina siempre.
                    if sig in seen or len(variants[sig]) > 1:
                        continue
                    seen.add(sig)
            blocks.append(block)
        new_pages.append(Page(number=page.number, blocks=blocks, ocr=page.ocr))
    return Document(name=doc.name, pages=new_pages, warnings=list(doc.warnings))


# --------------------------------------------------------------------------- markdown

def _is_heading(text: str) -> bool:
    if len(text) > 70 or text.upper() != text:  # descartes baratos primero
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3 or len(text.split()) > 10:
        return False
    if ":" in text.rstrip(":"):
        return False
    return text.upper() == text and sum(c.isupper() for c in letters) == len(letters)


def _kv(text: str) -> tuple[str, str] | None:
    m = KV_RE.match(text)
    if not m:
        return None
    label, value = m.group(1).strip(), m.group(2).strip()
    if not any(c.isalpha() for c in label) or TIME_LIKE_RE.search(label):
        return None
    if value.startswith("//"):  # URLs
        return None
    return label, value


def _split_on_labels(segment: str) -> list[str]:
    """Separa "Nombre: X RUT: Y" en ["Nombre: X", "RUT: Y"] usando etiquetas conocidas."""
    cuts = [m.start() for m in NEXT_LABEL_RE.finditer(segment) if m.start() > 0]
    if not cuts:
        return [segment]
    bounds = [0] + cuts + [len(segment)]
    pieces = [segment[a:b].strip().rstrip(" -–,;").strip() for a, b in zip(bounds, bounds[1:], strict=False)]
    return [p for p in pieces if p]


def _md_escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _md_table(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    norm_rows = [[_md_escape_cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    header, body = norm_rows[0], norm_rows[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * width) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _render_page_markdown(page: Page, redact: Redact) -> list[str]:
    chunks: list[str] = []  # bloques separados por línea en blanco
    current: list[str] = []
    current_kind = None

    def flush() -> None:
        nonlocal current, current_kind
        if current:
            chunks.append("\n".join(current))
        current, current_kind = [], None

    def push(kind: str, line: str) -> None:
        nonlocal current_kind
        if current_kind != kind:
            flush()
            current_kind = kind
        current.append(line)

    for block in page.blocks:
        if block.kind == "table":
            flush()
            rows = [[redact(c) for c in row] for row in block.rows]
            chunks.append(_md_table(rows))
            continue

        raw = block.text.strip()
        if not raw:
            flush()
            continue
        text = redact(raw)

        if BULLET_RE.match(text):
            push("list", "- " + BULLET_RE.sub("", text, count=1))
            continue
        if NUMBERED_RE.match(text):
            push("olist", text)
            continue
        if _is_heading(WIDE_GAP_RE.sub(" ", text).rstrip(":")):
            flush()
            chunks.append("## " + WIDE_GAP_RE.sub(" ", text).rstrip(":").strip())
            continue

        segments = [s.strip() for s in WIDE_GAP_RE.split(text) if s.strip()]
        kvs = [_kv(s) for s in segments]
        if all(kvs):
            split = [piece for seg in segments for piece in _split_on_labels(seg)]
            split_kvs = [_kv(s) for s in split]
            if all(split_kvs):
                kvs = split_kvs
        pairs = [kv for kv in kvs if kv is not None]
        if len(pairs) == len(kvs):
            for label, value in pairs:
                push("kv", f"- **{label}:** {value}")
            continue
        if len(segments) == 1 and text.endswith(":") and len(text) <= 60:
            flush()
            chunks.append(f"**{text}**")
            continue

        line = "  ".join(segments)
        if current_kind == "para" and current and _continues(current[-1], line):
            current[-1] = current[-1] + " " + line
        else:
            push("para", line)
    flush()
    return chunks


def _continues(previous: str, line: str) -> bool:
    return bool(previous) and previous[-1] not in ".:;!?" and line[:1].islower()


def render_markdown(doc: Document, redact: Redact, lang: str, page_markers: bool) -> str:
    parts: list[str] = []
    multi = len(doc.pages) > 1
    for page in doc.pages:
        if page_markers and multi:
            if parts:
                parts.append("---")
            parts.append(f"*{PAGE_LABEL.get(lang, 'Página')} {page.number}*")
        if page.empty:
            parts.append(f"> {NO_TEXT_PAGE.get(lang, NO_TEXT_PAGE['es'])}")
            continue
        parts.extend(_render_page_markdown(page, redact))
    return "\n\n".join(parts).strip() + "\n"


# --------------------------------------------------------------------------- texto plano

def render_text(doc: Document, redact: Redact, lang: str, page_markers: bool) -> str:
    out: list[str] = []
    multi = len(doc.pages) > 1
    for page in doc.pages:
        if page_markers and multi:
            if out:
                out.append("")
            out.append(f"===== {PAGE_LABEL.get(lang, 'Página')} {page.number} =====")
            out.append("")
        if page.empty:
            out.append(NO_TEXT_PAGE.get(lang, NO_TEXT_PAGE["es"]))
            continue
        previous_blank = False
        for block in page.blocks:
            if block.kind == "table":
                out.extend(" | ".join(redact(c) for c in row) for row in block.rows)
                out.append("")
                previous_blank = True
                continue
            text = block.text.rstrip()
            if not text.strip():
                if not previous_blank:
                    out.append("")
                previous_blank = True
                continue
            out.append(redact(text))
            previous_blank = False
    return "\n".join(out).strip() + "\n"


def render(doc: Document, redact: Redact, fmt: str, lang: str, page_markers: bool) -> str:
    if fmt == "text":
        return render_text(doc, redact, lang, page_markers)
    return render_markdown(doc, redact, lang, page_markers)


__all__ = ["render", "strip_repeated_lines", "Block"]
