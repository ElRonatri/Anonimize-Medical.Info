"""Extracción de texto y tablas desde PDF / TXT hacia el modelo `Document`."""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdfplumber.page import Page as PdfPage
    from pdfplumber.table import Table as PdfTable

from . import ocr
from .document import Block, Document, Page
from .privacy import log_exception

log = logging.getLogger(__name__)

LINE_TOLERANCE = 3.0  # puntos: palabras con `top` similar pertenecen a la misma línea
WIDE_GAP_FACTOR = 3.0  # separaciones mayores a N anchos de carácter => columna distinta


class ExtractionError(Exception):
    pass


# Callback de progreso: (página_actual, total_páginas, etapa) con etapa "text" u "ocr".
Progress = Callable[[int, int, str], None]

OCR_AUTO, OCR_FORCE, OCR_OFF = "auto", "force", "off"
MIN_TEXT_CHARS = 25  # menos caracteres que esto + imagen grande => página escaneada


def load_document(path: str | Path, ocr_mode: str = OCR_AUTO, ocr_engine: str = "auto",
                  progress: Progress | None = None, use_ocr: bool | None = None) -> Document:
    path = Path(path)
    return load_bytes(path.name, path.read_bytes(), ocr_mode=ocr_mode, ocr_engine=ocr_engine,
                      progress=progress, use_ocr=use_ocr)


def load_bytes(name: str, data: bytes, ocr_mode: str = OCR_AUTO, ocr_engine: str = "auto",
               progress: Progress | None = None, use_ocr: bool | None = None) -> Document:
    if use_ocr is False:  # compatibilidad con la firma anterior
        ocr_mode = OCR_OFF
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" or data[:5] == b"%PDF-":
        return _load_pdf(name, data, ocr_mode, ocr_engine, progress)
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

def unrotated_copy(data: bytes) -> bytes | None:
    """Copia en memoria con /Rotate=0 en todas las páginas, o None si ninguna está rotada.

    Una página con /Rotate (p. ej. un informe apaisado) guarda su texto en la orientación natural
    de lectura; pdfplumber, en cambio, entrega las coordenadas ya rotadas y el texto sale
    desordenado o al revés (y entonces los nombres no se detectan). La capa de texto se lee de
    esta copia; el OCR sigue usando la página rotada, que es la que deja derecho un escaneo.
    """
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
    except Exception:
        return None
    try:
        pages = [doc[i] for i in range(len(doc))]
        if not any(p.get_rotation() for p in pages):
            return None
        for p in pages:
            p.set_rotation(0)
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()


def _load_pdf(name: str, data: bytes, ocr_mode: str, ocr_engine: str,
              progress: Progress | None) -> Document:
    import pdfplumber

    doc = Document(name=name)
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
        flat = unrotated_copy(data)
        text_pdf = pdfplumber.open(io.BytesIO(flat)) if flat is not None else pdf
    except Exception as exc:  # pdfminer lanza varios tipos distintos
        raise ExtractionError(f"invalid_pdf:{exc}") from exc

    engine = ocr.pick_engine(ocr_engine) if ocr_mode != OCR_OFF else None
    with pdf, text_pdf:
        total = len(pdf.pages)
        for index, pdf_page in enumerate(pdf.pages, start=1):
            if progress:
                progress(index, total, "text")
            page = Page(number=index)
            try:
                page.blocks = _extract_page_blocks(text_pdf.pages[index - 1])
            except Exception as exc:  # una página dañada no debe tumbar el documento
                log_exception(log, "Error extrayendo la página %s", exc, index)
                doc.warnings.append(f"page_error:{index}:{exc}")
                page.blocks = []

            if engine and _needs_ocr(pdf_page, page, ocr_mode):
                if progress:
                    progress(index, total, "ocr")
                try:
                    lines = ocr.ocr_page(pdf_page, engine)
                    if any(t.strip() for t in lines):
                        page.blocks = [Block("line", text=t) for t in lines]
                        page.ocr = True
                except Exception as exc:
                    log_exception(log, "Error de OCR en la página %s", exc, index)
                    doc.warnings.append(f"ocr_error:{index}:{exc}")
            doc.pages.append(page)

    if doc.pages and all(p.empty for p in doc.pages):
        doc.warnings.append("no_text_after_ocr" if engine else "no_text")
    elif any(p.empty for p in doc.pages) and not engine:
        doc.warnings.append("some_pages_without_text")
    if any(p.ocr for p in doc.pages):
        doc.ocr_engine = engine
    return doc


def _needs_ocr(pdf_page: PdfPage, page: Page, mode: str) -> bool:
    """¿Conviene reconocer esta página como imagen?"""
    if mode == OCR_FORCE or page.empty:
        return True
    chars = sum(len(b.flat_text().strip()) for b in page.blocks)
    if chars >= MIN_TEXT_CHARS:
        return False
    # Poco texto (p. ej. sólo un pie de página) y una imagen que cubre gran parte de la página.
    page_area = float(pdf_page.width * pdf_page.height) or 1.0
    try:
        image_area = sum(abs((im["x1"] - im["x0"]) * (im["bottom"] - im["top"])) for im in pdf_page.images)
    except Exception:
        return False
    return bool(image_area / page_area > 0.3)


def _extract_page_blocks(pdf_page: PdfPage) -> list[Block]:
    tables = []
    try:
        tables = [t for t in pdf_page.find_tables() if _table_is_meaningful(t)]
    except Exception:
        log.debug("Fallo detectando tablas en una página")

    bboxes = [t.bbox for t in tables]

    def outside_tables(obj: dict[str, Any]) -> bool:
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


def _table_is_meaningful(table: PdfTable) -> bool:
    rows = table.extract()
    if len(rows) < 2:
        return False
    max_cols = max((len(r) for r in rows), default=0)
    if max_cols < 2:
        return False
    filled = sum(1 for r in rows for c in r if c and str(c).strip())
    return filled >= 3


def _clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    return _fix_cid(" ".join(str(value).split()))


def _lines_from_words(page: PdfPage) -> list[tuple[float, str]]:
    """Reconstruye líneas a partir de palabras, preservando huecos grandes como '   '."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
    if not words:
        return []
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))

    lines: list[list[dict[str, Any]]] = []
    for word in words:
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])

    result = []
    for line_words in lines:
        line_words.sort(key=lambda w: w["x0"])
        parts = [line_words[0]["text"]]
        for prev, cur in zip(line_words, line_words[1:], strict=False):
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
