"""Garantías de privacidad operativa: logging sin contenido clínico.

Reglas:
* Los mensajes de log nunca incluyen texto de documentos, nombres de archivo (suelen contener
  el nombre del paciente), valores detectados ni opciones con términos del usuario.
* De las excepciones sólo se registra el TIPO y la pila de llamadas (archivo, línea, función).
  El mensaje de la excepción se omite: algunas lo construyen con fragmentos del contenido
  (p. ej. `UnicodeDecodeError` incluye los bytes que fallaron).
* Las librerías que leen el PDF (pdfminer, pdfplumber, PIL...) quedan en WARNING incluso en
  modo desarrollo: en DEBUG pdfminer puede volcar el contenido de las páginas.
"""

from __future__ import annotations

import logging
import sys
import traceback

# Librerías de terceros que procesan contenido del documento.
QUIET_LOGGERS = ("pdfminer", "pdfplumber", "PIL", "pypdfium2", "docx", "rapidocr", "RapidOCR",
                 "onnxruntime", "pytesseract", "bottle", "urllib3")


def exception_summary(exc: BaseException) -> str:
    """Tipo de la excepción y pila de llamadas, SIN el mensaje (que puede contener datos)."""
    frames = traceback.extract_tb(exc.__traceback__)
    stack = " <- ".join(f"{f.filename.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{f.lineno}:{f.name}"
                        for f in reversed(frames[-6:]))
    return f"{type(exc).__module__}.{type(exc).__qualname__} at {stack or '?'}"


def log_exception(logger: logging.Logger, message: str, exc: BaseException, *args: object) -> None:
    """Registra un error sin contenido clínico. `message` y `args` no deben llevar datos del documento."""
    logger.error(message + " [%s]", *args, exception_summary(exc))


def configure_logging(dev: bool = False) -> None:
    level = logging.DEBUG if dev else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    if sys.stderr is None:  # ejecutable sin consola (PyInstaller --windowed)
        root.addHandler(logging.NullHandler())
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
