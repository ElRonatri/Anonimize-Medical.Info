"""API expuesta a la interfaz React a través de `window.pywebview.api`."""

from __future__ import annotations

import base64
import logging
import threading
from pathlib import Path

import webview

from anonymizer import ExtractionError, anonymize_document, load_bytes, load_document, load_text
from anonymizer import __version__, ocr

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 80 * 1024 * 1024  # 80 MB


def _dialog_type(name: str):
    """Compatibilidad entre pywebview 4.x (OPEN_DIALOG) y 5.x+ (FileDialog.OPEN)."""
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None:
        return getattr(file_dialog, name)
    return getattr(webview, f"{name}_DIALOG")


def _error(code: str, detail: str = "") -> dict:
    return {"ok": False, "error": code, "detail": detail}


class Api:
    def __init__(self) -> None:
        self._window = None  # privado: pywebview no expone atributos que empiezan con "_"
        self._lock = threading.Lock()
        self._last_doc = None

    def _set_window(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------ info
    def get_app_info(self) -> dict:
        return {"version": __version__, "ocr_available": ocr.available()}

    # ------------------------------------------------------------------ entrada
    def open_file_dialog(self) -> str | None:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(
            _dialog_type("OPEN"),
            allow_multiple=False,
            file_types=("Documentos (*.pdf;*.txt)", "PDF (*.pdf)", "Texto (*.txt)"),
        )
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def process_file(self, path: str, options: dict | None = None) -> dict:
        try:
            file_path = Path(path)
            if not file_path.is_file():
                return _error("file_not_found", path)
            if file_path.stat().st_size > MAX_FILE_BYTES:
                return _error("file_too_large")
            doc = load_document(file_path)
        except ExtractionError as exc:
            return _error(str(exc).split(":", 1)[0], str(exc))
        except Exception as exc:  # pragma: no cover - errores inesperados
            log.exception("Error leyendo %s", path)
            return _error("read_error", str(exc))
        return self._run(doc, options, file_path.name)

    def process_base64(self, name: str, data_b64: str, options: dict | None = None) -> dict:
        try:
            if "," in data_b64[:100]:  # data URL "data:application/pdf;base64,...."
                data_b64 = data_b64.split(",", 1)[1]
            data = base64.b64decode(data_b64)
            if len(data) > MAX_FILE_BYTES:
                return _error("file_too_large")
            doc = load_bytes(name, data)
        except ExtractionError as exc:
            return _error(str(exc).split(":", 1)[0], str(exc))
        except Exception as exc:  # pragma: no cover
            log.exception("Error leyendo %s", name)
            return _error("read_error", str(exc))
        return self._run(doc, options, name)

    def process_text(self, text: str, options: dict | None = None) -> dict:
        if not text or not text.strip():
            return _error("empty_text")
        return self._run(load_text(text), options, None)

    def reprocess(self, options: dict | None = None) -> dict:
        """Vuelve a anonimizar el último documento con otras opciones (sin releer el PDF)."""
        if self._last_doc is None:
            return _error("no_document")
        return self._run(self._last_doc, options, None, keep_doc=True)

    def _run(self, doc, options, file_name, keep_doc=False) -> dict:
        with self._lock:
            try:
                result = anonymize_document(doc, options)
            except Exception as exc:  # pragma: no cover
                log.exception("Error anonimizando")
                return _error("process_error", str(exc))
            if not keep_doc:
                self._last_doc = doc
        result["ok"] = True
        if file_name:
            result["file_name"] = file_name
        return result

    # ------------------------------------------------------------------ salida
    def save_result(self, content: str, suggested_name: str = "anonimizado.md") -> dict:
        if self._window is None:
            return _error("no_window")
        result = self._window.create_file_dialog(
            _dialog_type("SAVE"),
            save_filename=suggested_name,
            file_types=("Markdown (*.md)", "Texto (*.txt)", "Todos (*.*)"),
        )
        if not result:
            return {"ok": False, "cancelled": True}
        target = result[0] if isinstance(result, (list, tuple)) else str(result)
        try:
            Path(target).write_text(content, encoding="utf-8")
        except OSError as exc:
            return _error("write_error", str(exc))
        return {"ok": True, "path": target}

    def copy_to_clipboard(self, text: str) -> dict:
        try:
            import pyperclip

            pyperclip.copy(text)
            return {"ok": True}
        except Exception as exc:
            return _error("clipboard_error", str(exc))
