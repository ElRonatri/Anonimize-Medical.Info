"""OCR local (100% sin conexión) para PDFs escaneados o basados en imágenes.

Motores soportados (se usa el primero disponible, o el elegido por el usuario):

* **Tesseract**: requiere el ejecutable de Tesseract. Se busca en `TESSERACT_CMD`, en una
  carpeta `tesseract/` junto a la aplicación (empaquetado con `build.bat --tesseract`), en el
  PATH y en las rutas de instalación típicas de Windows. Usa español + inglés si están instalados.
* **RapidOCR** (ONNX): todo en paquetes de pip, modelos incluidos.

Sin descargas: RapidOCR descargaría de internet los modelos que le falten. Aquí se le pasan
SIEMPRE las rutas de los modelos incluidos en el paquete; si falta alguno, el motor se considera
no disponible (nunca se intenta descargar). Además, el proceso bloquea la red (privacy.block_network).

Privacidad: ninguna imagen ni texto se escribe en disco. La página rasterizada se envía a
Tesseract por stdin y el texto se lee de stdout (sin archivos temporales); RapidOCR trabaja
en memoria.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdfplumber.page import Page as PdfPage

log = logging.getLogger(__name__)

TESSERACT = "tesseract"
RAPIDOCR = "rapidocr"
ENGINES = (TESSERACT, RAPIDOCR)

_lock = threading.Lock()
_rapid_engine = None
# Hilos por motor OCR. None = los que el motor decida (todos los núcleos). En los procesos de
# extracción en paralelo se reparte: núcleos / procesos (si no, se pelean por la CPU).
_thread_limit: int | None = None


def set_thread_limit(threads: int | None) -> None:
    global _thread_limit, _rapid_engine
    _thread_limit = threads
    _rapid_engine = None  # se recrea con el nuevo límite
_cache: dict[str, Any] = {}

_WINDOWS_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
)


def _app_dirs() -> list[Path]:
    dirs = []
    if getattr(sys, "_MEIPASS", None):
        dirs.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]  # sólo en PyInstaller
    dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path(__file__).resolve().parents[2])  # raíz del proyecto en desarrollo
    return dirs


def find_tesseract() -> str | None:
    if "tesseract_cmd" in _cache:
        cached: str | None = _cache["tesseract_cmd"]
        return cached
    candidates = [os.environ.get("TESSERACT_CMD", "")]
    for base in _app_dirs():
        candidates += [str(base / "tesseract" / "tesseract.exe"), str(base / "tesseract" / "tesseract")]
    candidates.append(shutil.which("tesseract") or "")
    if os.name == "nt":
        candidates += list(_WINDOWS_PATHS)
    found = next((c for c in candidates if c and Path(c).is_file()), None)
    _cache["tesseract_cmd"] = found
    return found


def _tesseract_env(cmd: str) -> dict[str, str]:
    env = dict(os.environ)
    if _thread_limit is not None:
        env["OMP_THREAD_LIMIT"] = str(_thread_limit)  # OpenMP de Tesseract
    tessdata = Path(cmd).parent / "tessdata"
    if tessdata.is_dir() and "TESSDATA_PREFIX" not in env:  # Tesseract empaquetado/portable
        env["TESSDATA_PREFIX"] = str(tessdata)
    return env


def _run_tesseract(
    args: list[str], data: bytes | None = None, timeout: float = 180,
) -> subprocess.CompletedProcess[bytes]:
    cmd = find_tesseract()
    if cmd is None:
        raise RuntimeError("tesseract_not_found")
    # En Windows, sin esto cada llamada abriría una ventana de consola sobre la aplicación.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run([cmd, *args], input=data, capture_output=True, timeout=timeout,
                          env=_tesseract_env(cmd), creationflags=flags, check=False)


def _tesseract_ready() -> bool:
    return find_tesseract() is not None


# Modelos que RapidOCR usa por defecto (se buscan dentro del propio paquete `rapidocr/models`).
_RAPID_MODELS = {"Det.model_path": "*det*.onnx", "Rec.model_path": "*rec*.onnx", "Cls.model_path": "*cls*.onnx"}


def rapid_model_paths() -> dict[str, str] | None:
    """Rutas de los modelos empaquetados con rapidocr, o None si falta alguno."""
    if "rapid_models" not in _cache:
        paths: dict[str, str] | None = None
        try:
            import numpy  # noqa: F401
            import rapidocr

            models_dir = Path(rapidocr.__file__).resolve().parent / "models"
            found = {key: sorted(models_dir.glob(pattern)) for key, pattern in _RAPID_MODELS.items()}
            if all(found.values()):
                paths = {key: str(files[0]) for key, files in found.items()}
            else:
                log.warning("RapidOCR sin modelos incluidos: el motor queda desactivado (no se descargan)")
        except ImportError:
            paths = None
        _cache["rapid_models"] = paths
    models: dict[str, str] | None = _cache["rapid_models"]
    return models


def _rapidocr_ready() -> bool:
    return rapid_model_paths() is not None


def available_engines() -> list[str]:
    if "engines" not in _cache:
        engines = []
        if _tesseract_ready():
            engines.append(TESSERACT)
        if _rapidocr_ready():
            engines.append(RAPIDOCR)
        _cache["engines"] = engines
    return list(_cache["engines"])


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
            out = _run_tesseract(["--list-langs"], timeout=30).stdout.decode("utf-8", "replace")
            installed = {line.strip() for line in out.splitlines()[1:]}
            chosen = [code for code in ("spa", "eng") if code in installed]
            langs = "+".join(chosen) if chosen else "eng"
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:  # pragma: no cover
            log.debug("No se pudieron listar los idiomas de Tesseract (%s)", type(exc).__name__)
        _cache["tess_langs"] = langs
    cached_langs: str = _cache["tess_langs"]
    return cached_langs


def info() -> dict[str, Any]:
    engines = available_engines()
    return {
        "available": bool(engines),
        "engines": engines,
        "tesseract_languages": tesseract_languages() if TESSERACT in engines else None,
    }


# --------------------------------------------------------------------------- OCR

def ocr_page(pdf_page: PdfPage, engine: str | None = None) -> list[str]:
    """Rasteriza una página de pdfplumber y devuelve sus líneas de texto ordenadas."""
    engine = pick_engine(engine)
    if engine == TESSERACT:
        return _ocr_tesseract(pdf_page)
    if engine == RAPIDOCR:
        return _ocr_rapid(pdf_page)
    raise RuntimeError("no_ocr_engine")


def _ocr_tesseract(pdf_page: PdfPage, resolution: int = 300) -> list[str]:
    image = pdf_page.to_image(resolution=resolution).original.convert("L")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    # stdin/stdout: la imagen nunca toca el disco. preserve_interword_spaces conserva los
    # huecos entre columnas ("Nombre: X     RUT: Y").
    proc = _run_tesseract(["stdin", "stdout", "-l", tesseract_languages(), "--psm", "3",
                           "-c", "preserve_interword_spaces=1"], data=buffer.getvalue())
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract_exit_{proc.returncode}")  # stderr no se propaga: puede citar el texto
    return [line.rstrip() for line in proc.stdout.decode("utf-8", "replace").splitlines()]


def _get_rapid() -> Any:  # rapidocr.RapidOCR (dependencia opcional)
    global _rapid_engine
    with _lock:
        if _rapid_engine is None:
            paths = rapid_model_paths()
            if paths is None:
                raise RuntimeError("rapidocr_models_missing")
            from rapidocr import RapidOCR

            # Rutas explícitas: RapidOCR nunca entra en su rama de descarga de modelos.
            params: dict[str, Any] = {**paths, "Global.log_level": "warning"}
            if _thread_limit is not None:
                params["EngineConfig.onnxruntime.intra_op_num_threads"] = _thread_limit
                params["EngineConfig.onnxruntime.inter_op_num_threads"] = 1
            _rapid_engine = RapidOCR(params=params)
    return _rapid_engine


def _ocr_rapid(pdf_page: PdfPage, resolution: int = 200) -> list[str]:
    import numpy as np

    image = pdf_page.to_image(resolution=resolution).original.convert("RGB")
    result = _get_rapid()(np.array(image))

    items: list[tuple[float, float, float, str]] = []  # (y_centro, x, alto, texto)
    pairs: Iterable[tuple[Any, Any]]
    if hasattr(result, "boxes"):  # rapidocr >= 2
        boxes = result.boxes if result.boxes is not None else []
        pairs = zip(boxes, result.txts or [], strict=False)
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
