"""Extracción de texto y tablas desde PDF / TXT hacia el modelo `Document`."""

from __future__ import annotations

import io
import re
import logging
from pathlib import Path

from .document import Block, Document, Page
from . import ocr

log = logging.getLogger(__name__)

LINE_TOLERANCE = 3.0  # puntos: palabras con `top` similar pertenecen a la misma línea
WIDE_GAP_FACTOR = 3.0  # separaciones mayores a N anchos de carácter => columna distinta


class ExtractionError(Exception):
    pass


def load_document(path: str | Path, use_ocr: bool = True) -> Document:
    path = Path(path)
    data = path.read_bytes()
    return load_bytes(path.name, data, use_ocr=use_ocr)


def load_bytes(name: str, data: bytes, use_ocr: bool = True) -> Document:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" or data[:5] == b"%PDF-":
        return _load_pdf(name, data, use_ocr)
    if suffix in (".txt", ".md", ".text", ""):
        return load_text(_decode(data), name=name)
    raise ExtractionError(f"unsupported:{suffix}")


def load_text(text: str, name: str = "texto") -> Document:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pages_raw = text.split("\f")
    doc = Document(name=name)
    for i, raw in enumerate(pages_raw, start=1):
        page = Page(number=i)
        page.blocks = [Block("line", text=line.rstrip()) for line in raw.split("\n")]
        doc.pages.append(page)
    return doc


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- PDF

def _load_pdf(name: str, data: bytes, use_ocr: bool) -> Document:
    import pdfplumber

    doc = Document(name=name)
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer lanza varios tipos distintos
        raise ExtractionError(f"invalid_pdf:{exc}") from exc

    with pdf:
        for index, pdf_page in enumerate(pdf.pages, start=1):
            page = Page(number=index)
            try:
                page.blocks = _extract_page_blocks(pdf_page)
            except Exception as exc:  # una página dañada no debe tumbar el documento
                log.exception("Error extrayendo página %s", index)
                doc.warnings.append(f"page_error:{index}:{exc}")
                page.blocks = []

            if page.empty and use_ocr and ocr.available():
                try:
                    lines = ocr.ocr_page(pdf_page)
                    page.blocks = [Block("line", text=t) for t in lines]
                    page.ocr = True
                except Exception as exc:
                    log.exception("Error de OCR en página %s", index)
                    doc.warnings.append(f"ocr_error:{index}:{exc}")
            doc.pages.append(page)

    if doc.pages and all(p.empty for p in doc.pages):
        doc.warnings.append("no_text" if not ocr.available() else "no_text_after_ocr")
    elif any(p.empty for p in doc.pages) and not ocr.available():
        doc.warnings.append("some_pages_without_text")
    return doc


def _extract_page_blocks(pdf_page) -> list[Block]:
    tables = []
    try:
        tables = [t for t in pdf_page.find_tables() if _table_is_meaningful(t)]
    except Exception:
        log.debug("Fallo detectando tablas", exc_info=True)

    bboxes = [t.bbox for t in tables]

    def outside_tables(obj) -> bool:
        if obj.get("object_type") != "char":
            return True
        cx = (obj["x0"] + obj["x1"]) / 2
        cy = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in bboxes)

    text_page = pdf_page.filter(outside_tables) if bboxes else pdf_page
    positioned: list[tuple[float, Block]] = [
        (top, Block("line", text=text)) for top, text in _lines_from_words(text_page)
    ]
    for table in tables:
        rows = []
        for row in table.extract():
            cells = [_clean_cell(c) for c in row]
            if any(cells):
                rows.append(cells)
        if rows:
            positioned.append((table.bbox[1], Block("table", rows=rows)))

    positioned.sort(key=lambda item: item[0])
    return [block for _, block in positioned]


def _table_is_meaningful(table) -> bool:
    rows = table.extract()
    if len(rows) < 2:
        return False
    max_cols = max((len(r) for r in rows), default=0)
    if max_cols < 2:
        return False
    filled = sum(1 for r in rows for c in r if c and str(c).strip())
    return filled >= 3


def _clean_cell(value) -> str:
    if value is None:
        return ""
    return _fix_cid(" ".join(str(value).split()))


def _lines_from_words(page) -> list[tuple[float, str]]:
    """Reconstruye líneas a partir de palabras, preservando huecos grandes como '   '."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
    if not words:
        return []
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))

    lines: list[list[dict]] = []
    for word in words:
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])

    result = []
    for line_words in lines:
        line_words.sort(key=lambda w: w["x0"])
        parts = [line_words[0]["text"]]
        for prev, cur in zip(line_words, line_words[1:]):
            char_w = max((prev["x1"] - prev["x0"]) / max(len(prev["text"]), 1), 2.0)
            gap = cur["x0"] - prev["x1"]
            parts.append("   " if gap > WIDE_GAP_FACTOR * char_w else " ")
            parts.append(cur["text"])
        text = _fix_cid("".join(parts).strip())
        if text:
            result.append((line_words[0]["top"], text))
    return result


_CID_RE = re.compile(r"\(cid:\d+\)")


def _fix_cid(text: str) -> str:
    """Glifos sin mapeo Unicode (p. ej. viñetas) aparecen como "(cid:127)"."""
    if text.startswith("(cid:"):
        text = _CID_RE.sub("•", text, count=1)
    return _CID_RE.sub("", text).strip()
