"""OCR local (100% sin conexión) para PDFs escaneados o basados en imágenes.

Motores soportados (se usa el primero disponible, o el elegido por el usuario):

* **Tesseract** vía `pytesseract`: requiere el ejecutable de Tesseract. Se busca en
  `TESSERACT_CMD`, en una carpeta `tesseract/` junto a la aplicación (empaquetado con
  `build.bat --tesseract`), en el PATH y en las rutas de instalación típicas de Windows.
  Usa los idiomas español + inglés si están instalados.
* **RapidOCR** (ONNX): todo en paquetes de pip, modelos incluidos.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

TESSERACT = "tesseract"
RAPIDOCR = "rapidocr"
ENGINES = (TESSERACT, RAPIDOCR)

_lock = threading.Lock()
_rapid_engine = None
_cache: dict[str, object] = {}

_WINDOWS_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
)


def _app_dirs() -> list[Path]:
    dirs = []
    if getattr(sys, "_MEIPASS", None):
        dirs.append(Path(sys._MEIPASS))
    dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path(__file__).resolve().parents[2])  # raíz del proyecto en desarrollo
    return dirs


def find_tesseract() -> str | None:
    if "tesseract_cmd" in _cache:
        return _cache["tesseract_cmd"]  # type: ignore[return-value]
    candidates = [os.environ.get("TESSERACT_CMD", "")]
    for base in _app_dirs():
        candidates += [str(base / "tesseract" / "tesseract.exe"), str(base / "tesseract" / "tesseract")]
    candidates.append(shutil.which("tesseract") or "")
    if os.name == "nt":
        candidates += list(_WINDOWS_PATHS)
    found = next((c for c in candidates if c and Path(c).is_file()), None)
    if found:
        tessdata = Path(found).parent / "tessdata"
        if tessdata.is_dir() and not os.environ.get("TESSDATA_PREFIX"):
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
    _cache["tesseract_cmd"] = found
    return found


def _tesseract_ready() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return find_tesseract() is not None


def _rapidocr_ready() -> bool:
    try:
        import numpy  # noqa: F401
        try:
            import rapidocr  # noqa: F401
        except ImportError:
            import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def available_engines() -> list[str]:
    if "engines" not in _cache:
        engines = []
        if _tesseract_ready():
            engines.append(TESSERACT)
        if _rapidocr_ready():
            engines.append(RAPIDOCR)
        _cache["engines"] = engines
    return list(_cache["engines"])  # type: ignore[arg-type]


def available() -> bool:
    return bool(available_engines())


def pick_engine(preferred: str | None = "auto") -> str | None:
    engines = available_engines()
    if preferred in engines:
        return preferred
    return engines[0] if engines else None


def tesseract_languages() -> str:
    if "tess_langs" not in _cache:
        langs = "eng"
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = find_tesseract()
            installed = set(pytesseract.get_languages(config=""))
            chosen = [code for code in ("spa", "eng") if code in installed]
            langs = "+".join(chosen) if chosen else "eng"
        except Exception:  # pragma: no cover - depende del sistema
            log.debug("No se pudieron listar los idiomas de Tesseract", exc_info=True)
        _cache["tess_langs"] = langs
    return _cache["tess_langs"]  # type: ignore[return-value]


def info() -> dict:
    engines = available_engines()
    return {
        "available": bool(engines),
        "engines": engines,
        "tesseract_languages": tesseract_languages() if TESSERACT in engines else None,
    }


# --------------------------------------------------------------------------- OCR

def ocr_page(pdf_page, engine: str | None = None) -> list[str]:
    """Rasteriza una página de pdfplumber y devuelve sus líneas de texto ordenadas."""
    engine = pick_engine(engine)
    if engine == TESSERACT:
        return _ocr_tesseract(pdf_page)
    if engine == RAPIDOCR:
        return _ocr_rapid(pdf_page)
    raise RuntimeError("no_ocr_engine")


def _ocr_tesseract(pdf_page, resolution: int = 300) -> list[str]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = find_tesseract()
    image = pdf_page.to_image(resolution=resolution).original.convert("L")
    # preserve_interword_spaces conserva los huecos entre columnas ("Nombre: X     RUT: Y").
    text = pytesseract.image_to_string(
        image, lang=tesseract_languages(), config="--psm 3 -c preserve_interword_spaces=1"
    )
    return [line.rstrip() for line in text.splitlines()]


def _get_rapid():
    global _rapid_engine
    with _lock:
        if _rapid_engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR
            _rapid_engine = RapidOCR()
    return _rapid_engine


def _ocr_rapid(pdf_page, resolution: int = 200) -> list[str]:
    import numpy as np

    image = pdf_page.to_image(resolution=resolution).original.convert("RGB")
    result = _get_rapid()(np.array(image))

    items: list[tuple[float, float, float, str]] = []  # (y_centro, x, alto, texto)
    if hasattr(result, "boxes"):  # rapidocr >= 2
        boxes = result.boxes if result.boxes is not None else []
        pairs = zip(boxes, result.txts or [])
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
