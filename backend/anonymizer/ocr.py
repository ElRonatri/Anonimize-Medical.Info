"""OCR opcional para PDFs escaneados.

Se activa sólo si el paquete `rapidocr` (o el antiguo `rapidocr_onnxruntime`) está
instalado. Funciona 100% local, sin servicios externos.
"""

from __future__ import annotations

import threading

_engine = None
_lock = threading.Lock()
_checked = False
_available = False


def available() -> bool:
    global _checked, _available
    if not _checked:
        _checked = True
        try:
            import numpy  # noqa: F401
            try:
                import rapidocr  # noqa: F401
            except ImportError:
                import rapidocr_onnxruntime  # noqa: F401
            _available = True
        except ImportError:
            _available = False
    return _available


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
    return _engine


def ocr_page(pdf_page, resolution: int = 200) -> list[str]:
    """Rasteriza una página de pdfplumber y devuelve sus líneas de texto ordenadas."""
    import numpy as np

    image = pdf_page.to_image(resolution=resolution).original.convert("RGB")
    result = _get_engine()(np.array(image))

    items: list[tuple[float, float, float, str]] = []  # (y_centro, x, alto, texto)
    if hasattr(result, "boxes"):  # rapidocr >= 2
        boxes = result.boxes if result.boxes is not None else []
        txts = result.txts or []
        pairs = zip(boxes, txts)
    else:  # rapidocr_onnxruntime: (lista, tiempos)
        raw = result[0] if isinstance(result, tuple) else result
        pairs = ((r[0], r[1]) for r in (raw or []))

    for box, text in pairs:
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), str(text)))

    items.sort()
    lines: list[list[tuple[float, float, float, str]]] = []
    for item in items:
        if lines and abs(lines[-1][0][0] - item[0]) < max(item[2], 1) * 0.5:
            lines[-1].append(item)
        else:
            lines.append([item])
    return ["   ".join(t for *_, t in sorted(line, key=lambda i: i[1])) for line in lines]
