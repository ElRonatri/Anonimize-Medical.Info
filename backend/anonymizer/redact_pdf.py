"""PDF censurado: el mismo documento, página por página, con los datos tapados.

Cada página se reproduce con su mismo tamaño y aspecto, y los datos detectados se cubren con
un recuadro negro (opcionalmente con su marcador, p. ej. ``[PACIENTE_1]``).

Diseño (privacidad primero):

* **Censura irreversible.** La página se renderiza a imagen (pypdfium2) y el recuadro se pinta
  sobre los píxeles; el PDF resultante sólo contiene esas imágenes. No queda capa de texto,
  metadatos, anotaciones, formularios, adjuntos ni JavaScript del original que pudieran
  conservar el dato bajo el recuadro (el error clásico de "tapar" con un rectángulo encima).
* **Mismas decisiones que el texto exportado.** Se usa el mismo `Redactor` (mismas reglas,
  excepciones y numeración de marcadores) sobre el texto de cada página, reconstruido con la
  posición de cada carácter (pdfplumber) o de cada palabra (OCR en páginas escaneadas).
* **Red de seguridad.** Todo valor que se ocultó en el texto se busca además en cada página (sin
  tildes ni mayúsculas, con espacios flexibles); si alguno no se logra ubicar, el informe lo
  dice (por marcador, nunca con el valor) para que el usuario revise.
* **Sin archivos temporales:** todo ocurre en memoria; sólo se escribe el PDF que el usuario guarda.

Limitaciones: texto dentro de imágenes de páginas con texto seleccionable (logos, firmas
escaneadas) no se detecta salvo con OCR "Todas las páginas"; anotaciones y campos de formulario
se omiten porque no se pueden revisar.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import ocr
from .detector import Redactor, compile_terms, norm
from .document import Document
from .extract import LINE_TOLERANCE, WIDE_GAP_FACTOR, unrotated_copy
from .pipeline import anonymize_with_redactor
from .privacy import log_exception

if TYPE_CHECKING:
    from pdfplumber.page import Page as PdfPage

log = logging.getLogger(__name__)

ALLOWED_DPI = (150, 200, 300)
DEFAULT_DPI = 200
JPEG_QUALITY = 88
PAD = 1.2  # puntos de margen alrededor de cada dato

Progress = Callable[[int, int], None]


@dataclass
class Box:
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class PageMap:
    """Texto de una página y la caja (en puntos, marco de pdfplumber) de cada carácter."""

    text: str = ""
    boxes: list[Box | None] = field(default_factory=list)

    def add(self, text: str, box: Box | None) -> None:
        self.text += text
        self.boxes.extend([box] * len(text))


@dataclass
class Redaction:
    rects: list[Box]
    label: str


# --------------------------------------------------------------------------- texto con posiciones

def _line_join(page_map: PageMap, words: list[tuple[str, list[Box], float]]) -> None:
    """Une las palabras de una línea con la misma regla de huecos que la extracción de texto."""
    for i, (text, boxes, _) in enumerate(words):
        if i:
            prev_text, prev_boxes, _ = words[i - 1]
            char_w = max((prev_boxes[-1].x1 - prev_boxes[0].x0) / max(len(prev_text), 1), 2.0)
            gap = boxes[0].x0 - prev_boxes[-1].x1
            page_map.add("   " if gap > WIDE_GAP_FACTOR * char_w else " ", None)
        for ch, box in zip(text, boxes, strict=False):
            page_map.add(ch, box)
    page_map.add("\n", None)


def map_text_page(pdf_page: PdfPage) -> PageMap:
    """Texto de una página con capa de texto, carácter por carácter."""
    words = pdf_page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5,
                                   return_chars=True)
    items: list[tuple[str, list[Box], float]] = []
    for w in words:
        text, boxes = "", []
        for c in w.get("chars", []):
            box = Box(float(c["x0"]), float(c["top"]), float(c["x1"]), float(c["bottom"]))
            text += c["text"]
            boxes.extend([box] * len(c["text"]))
        if text:
            items.append((text, boxes, float(w["top"])))
    items.sort(key=lambda it: (round(it[2]), it[1][0].x0))
    lines: list[list[tuple[str, list[Box], float]]] = []
    for item in items:
        if lines and abs(lines[-1][0][2] - item[2]) <= LINE_TOLERANCE:
            lines[-1].append(item)
        else:
            lines.append([item])
    page_map = PageMap()
    for line in lines:
        _line_join(page_map, sorted(line, key=lambda it: it[1][0].x0))
    return page_map


def map_ocr_words(lines: list[list[ocr.OcrWord]]) -> PageMap:
    """Texto de una página escaneada: cada palabra reparte su caja entre sus caracteres."""
    page_map = PageMap()
    for line in lines:
        items: list[tuple[str, list[Box], float]] = []
        for text, x0, top, x1, bottom in line:
            step = (x1 - x0) / max(len(text), 1)
            boxes = [Box(x0 + i * step, top, x0 + (i + 1) * step, bottom) for i in range(len(text))]
            items.append((text, boxes, top))
        if items:
            _line_join(page_map, items)
    return page_map


# --------------------------------------------------------------------------- qué tapar

def _rects(boxes: list[Box]) -> list[Box]:
    """Une las cajas de un tramo en un rectángulo por línea."""
    rects: list[Box] = []
    for b in boxes:
        last = rects[-1] if rects else None
        if last and abs(((last.top + last.bottom) / 2) - ((b.top + b.bottom) / 2)) < (b.bottom - b.top) * 0.6:
            last.x0, last.x1 = min(last.x0, b.x0), max(last.x1, b.x1)
            last.top, last.bottom = min(last.top, b.top), max(last.bottom, b.bottom)
        else:
            rects.append(Box(b.x0, b.top, b.x1, b.bottom))
    return [Box(r.x0 - PAD, r.top - PAD, r.x1 + PAD, r.bottom + PAD) for r in rects]


def find_redactions(page_map: PageMap, redactor: Redactor,
                    originals: dict[str, str]) -> tuple[list[Redaction], set[str]]:
    """Tramos a tapar en una página y qué valores (normalizados) quedaron cubiertos en ella.

    `originals`: valor tal como apareció -> marcador, de todo lo que se ocultó en el texto exportado.
    """
    text = page_map.text
    spans = list(redactor.locate(text))
    by_norm = {norm(v): label for v, label in originals.items()}

    # Red de seguridad: cada valor ya ocultado se busca también literalmente (sin tildes ni
    # mayúsculas, espacios flexibles), salvo dentro de un término de la lista de excepciones.
    covered: set[str] = set()
    pattern = compile_terms(list(originals))
    if pattern is not None:
        allowed: list[tuple[int, int]] = []
        if redactor.knowledge.whitelist_re is not None:
            allowed = [(m.start(), m.end()) for m in redactor.knowledge.whitelist_re.finditer(text)]
        for m in pattern.finditer(text):
            if any(a <= m.start() and m.end() <= b for a, b in allowed):
                continue
            covered.add(norm(m.group(0)))
            if not any(s < m.end() and m.start() < e for s, e, _ in spans):
                spans.append((m.start(), m.end(), by_norm.get(norm(m.group(0)), "")))

    redactions: list[Redaction] = []
    for start, end, label in sorted(spans):
        boxes = [b for b in page_map.boxes[start:end] if b is not None]
        if boxes:
            covered.add(norm(text[start:end]))
            redactions.append(Redaction(_rects(boxes), label))
    return redactions, covered


# --------------------------------------------------------------------------- render y salida

def _frame_offset(page: Any, rotation: int) -> tuple[float, float]:
    """Desplazamiento de la cropbox (lo que se renderiza) en el marco de coordenadas de pdfplumber.

    pdfplumber mide desde la mediabox, ya rotada según /Rotate; pypdfium2 renderiza la cropbox.
    """
    ml, mb, mr, mt = page.get_mediabox()
    cl, cb, cr, ct = page.get_cropbox()

    def to_frame(x: float, y: float) -> tuple[float, float]:
        if rotation == 90:
            return y - mb, x - ml
        if rotation == 180:
            return mr - x, y - mb
        if rotation == 270:
            return mt - y, mr - x
        return x - ml, mt - y

    corners = [to_frame(x, y) for x in (cl, cr) for y in (cb, ct)]
    return min(c[0] for c in corners), min(c[1] for c in corners)


def _draw(image: Any, redactions: list[Redaction], scale: float, offset: tuple[float, float],
          labels: bool) -> None:
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    ox, oy = offset
    for red in redactions:
        for i, r in enumerate(red.rects):
            box = ((r.x0 - ox) * scale, (r.top - oy) * scale, (r.x1 - ox) * scale, (r.bottom - oy) * scale)
            draw.rectangle(box, fill="black")
            if not (labels and red.label and i == 0):
                continue
            height = box[3] - box[1]
            size = int(height * 0.62)
            if size < 7:
                continue
            font = ImageFont.load_default(size=size)
            width = draw.textlength(red.label, font=font)
            while width > (box[2] - box[0]) - 2 and size > 7:
                size -= 1
                font = ImageFont.load_default(size=size)
                width = draw.textlength(red.label, font=font)
            if width <= (box[2] - box[0]) - 2:
                draw.text((box[0] + 1, box[1] + (height - size) / 2 - 1), red.label, fill="white", font=font)


def _jpeg(image: Any) -> bytes:
    """JPEG de la página; en gris si la página no tiene color (más liviano)."""
    rgb = image.convert("RGB")
    small = rgb.resize((max(1, rgb.width // 8), max(1, rgb.height // 8)))
    raw = small.tobytes()  # RGB intercalado; funciona con cualquier versión de Pillow
    colorful = any(max(raw[i:i + 3]) - min(raw[i:i + 3]) > 24 for i in range(0, len(raw), 3))
    out = io.BytesIO()
    (rgb if colorful else rgb.convert("L")).save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def _annotation_count(page: Any) -> int:
    import pypdfium2.raw as raw

    try:
        return int(raw.FPDFPage_GetAnnotCount(page.raw))
    except Exception:
        return 0


def redact_pdf(data: bytes, doc: Document, options: dict[str, Any] | None = None, *,
               dpi: int = DEFAULT_DPI, labels: bool = True,
               progress: Progress | None = None) -> tuple[bytes, dict[str, Any]]:
    """Recrea el PDF `data` con los datos tapados. `doc` es su extracción (con OCR si lo hubo).

    Devuelve (bytes del PDF censurado, informe). El informe nunca incluye valores detectados.
    """
    import pdfplumber
    import pypdfium2 as pdfium

    dpi = dpi if dpi in ALLOWED_DPI else DEFAULT_DPI
    scale = dpi / 72.0
    result, redactor = anonymize_with_redactor(doc, options)
    # Todo lo que se ocultó en el texto exportado: valor tal como apareció -> marcador.
    originals = {v: e["placeholder"] for e in result["entities"] for v in e["values"]}

    report: dict[str, Any] = {"pages": 0, "redactions": 0, "ocr_pages": 0, "annotations_removed": 0,
                              "dpi": dpi, "unlocated": [], "page_errors": []}
    located: set[str] = set()
    source = pdfium.PdfDocument(data)
    output = pdfium.PdfDocument.new()
    try:
        # Páginas con /Rotate: la capa de texto se lee y se dibuja sobre una copia sin rotar
        # (orientación natural del texto) y la imagen se rota al final; el OCR usa la página rotada.
        flat_bytes = unrotated_copy(data)
        flat = pdfium.PdfDocument(flat_bytes) if flat_bytes is not None else source
        with pdfplumber.open(io.BytesIO(data)) as plumber, \
                pdfplumber.open(io.BytesIO(flat_bytes if flat_bytes is not None else data)) as plumber_flat:
            total = len(plumber.pages)
            for index in range(total):
                if progress:
                    progress(index + 1, total)
                page = source[index]
                rotation = page.get_rotation()
                width_pt, height_pt = page.get_size()  # tamaño exacto, ya con /Rotate aplicado
                extracted = doc.pages[index] if index < len(doc.pages) else None
                use_ocr = bool(extracted is not None and extracted.ocr and doc.ocr_engine)
                redactions: list[Redaction] = []
                try:
                    if use_ocr:
                        page_map = map_ocr_words(ocr.ocr_word_lines(plumber.pages[index], doc.ocr_engine))
                        report["ocr_pages"] += 1
                    else:
                        page_map = map_text_page(plumber_flat.pages[index])
                    redactions, found = find_redactions(page_map, redactor, originals)
                    located |= found
                except Exception as exc:  # la página se reproduce igual; el informe lo advierte
                    log_exception(log, "Error ubicando datos en la página %s", exc, index + 1)
                    report["page_errors"].append(index + 1)

                if use_ocr or not rotation:
                    target, post_rotation = page, 0
                else:
                    target, post_rotation = flat[index], rotation
                bitmap = target.render(scale=scale, may_draw_forms=False, draw_annots=False)
                image = bitmap.to_pil()
                _draw(image, redactions, scale, _frame_offset(target, target.get_rotation()), labels)
                if post_rotation:  # /Rotate gira en sentido horario; PIL, antihorario
                    image = image.rotate(-post_rotation, expand=True)
                report["redactions"] += sum(len(r.rects) for r in redactions)
                report["annotations_removed"] += _annotation_count(page)

                new_page = output.new_page(width_pt, height_pt)
                pdf_image = pdfium.PdfImage.new(output)
                pdf_image.load_jpeg(io.BytesIO(_jpeg(image)), inline=False, autoclose=True)
                pdf_image.set_matrix(pdfium.PdfMatrix().scale(width_pt, height_pt))
                new_page.insert_obj(pdf_image)
                new_page.gen_content()
                report["pages"] += 1
                image.close()
                bitmap.close()
                if target is not page:
                    target.close()
                page.close()
                new_page.close()
        if flat is not source:
            flat.close()

        buffer = io.BytesIO()
        output.save(buffer)
    finally:
        output.close()
        source.close()

    report["unlocated"] = sorted({label for v, label in originals.items() if norm(v) not in located})
    return buffer.getvalue(), report


def synthetic_text_pdf(lines: list[str]) -> bytes:
    """PDF de una página con capa de texto, creado en memoria (autoprueba y sonda de privacidad)."""
    import ctypes
    import io

    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    doc = pdfium.PdfDocument.new()
    try:
        page = doc.new_page(595, 842)
        for i, line in enumerate(lines):
            obj = raw.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", ctypes.c_float(14))
            encoded = (line + "\0").encode("utf-16-le")
            raw.FPDFText_SetText(obj, (ctypes.c_ushort * (len(encoded) // 2)).from_buffer_copy(encoded))
            raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 80, 700 - 22 * i)
            raw.FPDFPage_InsertObject(page.raw, obj)
        page.gen_content()
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    finally:
        doc.close()
