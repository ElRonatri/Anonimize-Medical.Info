"""API expuesta a la interfaz React a través de `window.pywebview.api`.

El trabajo pesado (lectura de PDF y OCR) se ejecuta en un hilo secundario que consume una
cola de lotes; la interfaz consulta el avance con `get_job` sin bloquearse. Re-anonimizar
con otras opciones usa los documentos ya extraídos en memoria y toma milisegundos.
"""

from __future__ import annotations

import base64
import logging
import queue
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from anonymizer import ExtractionError, __version__, anonymize_document, identifiers, load_bytes, load_text, ocr
from anonymizer.document import Document
from anonymizer.exporters import FORMATS, export_bytes
from anonymizer.privacy import log_exception

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 80 * 1024 * 1024  # 80 MB por archivo


def _dialog_type(name: str):
    """Compatibilidad entre pywebview 4.x (OPEN_DIALOG) y 5.x+ (FileDialog.OPEN)."""
    import webview

    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None:
        return getattr(file_dialog, name)
    return getattr(webview, f"{name}_DIALOG")


def _error(code: str, detail: str = "") -> dict:
    return {"ok": False, "error": code, "detail": detail}


_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_stem(name: str | None, fallback: str = "documento") -> str:
    stem = Path(name or "").stem
    stem = _UNSAFE_NAME_RE.sub("_", stem).strip(" ._")
    return stem[:120] or fallback


@dataclass
class Item:
    id: str
    name: str
    path: str | None = None
    data: bytes | None = None
    doc: Document | None = None
    status: str = "queued"  # queued | processing | done | error | cancelled
    stage: str = ""  # text | ocr | anonymize
    page: int = 0
    pages: int = 0
    error: str = ""
    detail: str = ""
    result: dict | None = None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status, "stage": self.stage,
                "page": self.page, "pages": self.pages, "error": self.error, "detail": self.detail}


@dataclass
class Job:
    id: str
    item_ids: list[str]
    options: dict
    cancelled: bool = False
    done: bool = False
    current: str | None = None
    finished: set[str] = field(default_factory=set)


class Api:
    def __init__(self) -> None:
        self._window = None  # privado: pywebview no expone atributos que empiezan con "_"
        self._lock = threading.RLock()
        self._items: dict[str, Item] = {}
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None

    def _set_window(self, window) -> None:
        self._window = window

    # ------------------------------------------------------------------ info
    def get_app_info(self) -> dict:
        return {
            "version": __version__,
            "ocr": ocr.info(),
            "ocr_available": ocr.available(),
            "regions": {k: list(v) for k, v in identifiers.REGIONES.items()},
            "country_formats": identifiers.formatos_por_pais(),
            "export_formats": list(FORMATS),
        }

    # ------------------------------------------------------------------ selección de archivos
    def open_file_dialog(self) -> list[str]:
        if self._window is None:
            return []
        result = self._window.create_file_dialog(
            _dialog_type("OPEN"),
            allow_multiple=True,
            file_types=("Documentos (*.pdf;*.txt)", "PDF (*.pdf)", "Texto (*.txt)"),
        )
        if not result:
            return []
        return [str(p) for p in (result if isinstance(result, (list, tuple)) else [result])]

    # ------------------------------------------------------------------ lotes
    def start_batch(self, files: list[dict], options: dict | None = None) -> dict:
        """Encola archivos para procesarlos en segundo plano.

        `files`: [{"path": "C:/..."} | {"name": "x.pdf", "data": "<base64 o data URL>"}]
        """
        items, rejected = [], []
        for f in files or []:
            name = f.get("name") or Path(f.get("path") or "documento").name
            item = Item(id=uuid.uuid4().hex[:12], name=name, path=f.get("path"))
            if f.get("data") is not None:
                try:
                    data = f["data"]
                    if "," in data[:100]:  # data URL "data:application/pdf;base64,...."
                        data = data.split(",", 1)[1]
                    item.data = base64.b64decode(data)
                except Exception as exc:
                    item.status, item.error, item.detail = "error", "read_error", str(exc)
            if item.data is not None and len(item.data) > MAX_FILE_BYTES:
                item.status, item.error, item.data = "error", "file_too_large", None
            if item.path is None and item.data is None and item.status != "error":
                item.status, item.error = "error", "file_not_found"
            items.append(item)
            if item.status == "error":
                rejected.append(item.id)
        with self._lock:
            for item in items:
                self._items[item.id] = item
        job = self._enqueue([i.id for i in items if i.id not in rejected], options)
        return {"ok": True, "job_id": job.id, "items": [i.public() for i in items]}

    def reload_items(self, item_ids: list[str], options: dict | None = None) -> dict:
        """Vuelve a extraer (p. ej. tras cambiar el modo de OCR) documentos ya cargados."""
        with self._lock:
            ids = [i for i in item_ids or [] if i in self._items
                   and (self._items[i].path or self._items[i].data)]
            for i in ids:
                item = self._items[i]
                item.status, item.stage, item.page, item.error, item.detail = "queued", "", 0, "", ""
        job = self._enqueue(ids, options)
        return {"ok": True, "job_id": job.id, "items": [self._items[i].public() for i in ids]}

    def _enqueue(self, ids: list[str], options: dict | None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], item_ids=ids, options=dict(options or {}))
        with self._lock:
            self._jobs[job.id] = job
            if not ids:
                job.done = True
                return job
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._work, name="anonymizer-worker", daemon=True)
                self._worker.start()
        self._queue.put(job.id)
        return job

    def get_job(self, job_id: str, known: list[str] | None = None) -> dict:
        """Estado del lote. Incluye el resultado de cada archivo terminado sólo una vez."""
        known_set = set(known or [])
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return _error("no_job")
            items = [self._items[i] for i in job.item_ids if i in self._items]
            results = {i.id: i.result for i in items
                       if i.status == "done" and i.result and i.id not in known_set}
            return {
                "ok": True,
                "done": job.done,
                "cancelled": job.cancelled,
                "current": job.current,
                "total": len(items),
                "completed": sum(1 for i in items if i.status in ("done", "error", "cancelled")),
                "items": [i.public() for i in items],
                "results": results,
            }

    def cancel_job(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return _error("no_job")
            job.cancelled = True
        return {"ok": True}

    def remove_items(self, item_ids: list[str]) -> dict:
        with self._lock:
            for i in item_ids or []:
                self._items.pop(i, None)
        return {"ok": True}

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                job = self._jobs.get(job_id)
            if job is None:
                continue
            for item_id in job.item_ids:
                with self._lock:
                    item = self._items.get(item_id)
                    if item is None:
                        continue
                    if job.cancelled:
                        item.status = "cancelled"
                        continue
                    job.current = item_id
                    item.status, item.stage, item.page = "processing", "text", 0
                self._process_item(item, job)
            with self._lock:
                job.current = None
                job.done = True

    def _process_item(self, item: Item, job: Job) -> None:
        opts = job.options

        def progress(page: int, total: int, stage: str) -> None:
            with self._lock:
                item.page, item.pages, item.stage = page, total, stage

        try:
            if item.data is None and item.path:
                path = Path(item.path)
                if not path.is_file():
                    raise ExtractionError("file_not_found")
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ExtractionError("file_too_large")
                item.data = path.read_bytes()
            doc = load_bytes(item.name, item.data or b"", ocr_mode=opts.get("ocr_mode", "auto"),
                             ocr_engine=opts.get("ocr_engine", "auto"), progress=progress)
            with self._lock:
                item.stage = "anonymize"
            result = self._anonymize(doc, opts, item)
            with self._lock:
                item.doc, item.result, item.status, item.pages = doc, result, "done", result["pages"]
        except ExtractionError as exc:
            with self._lock:
                item.status, item.error, item.detail = "error", str(exc).split(":", 1)[0], str(exc)
        except Exception as exc:  # pragma: no cover - errores inesperados
            log_exception(log, "Error procesando el elemento %s", exc, item.id)
            with self._lock:
                item.status, item.error, item.detail = "error", "process_error", str(exc)

    @staticmethod
    def _anonymize(doc, options: dict, item: Item) -> dict:
        result = anonymize_document(doc, options)
        result["ok"] = True
        result["id"] = item.id
        result["file_name"] = item.name
        return result

    # ------------------------------------------------------------------ texto pegado
    def process_text(self, text: str, options: dict | None = None) -> dict:
        if not text or not text.strip():
            return _error("empty_text")
        item = Item(id=uuid.uuid4().hex[:12], name="texto", status="done")
        item.doc = load_text(text, name="texto")
        item.result = self._anonymize(item.doc, options or {}, item)
        item.pages = item.result["pages"]
        with self._lock:
            self._items[item.id] = item
        return {"ok": True, "item": item.public(), "result": item.result}

    # ------------------------------------------------------------------ re-anonimizar
    def reprocess(self, options: dict | None = None, item_ids: list[str] | None = None) -> dict:
        """Re-anonimiza documentos ya extraídos con nuevas opciones (sin releer los PDF)."""
        with self._lock:
            ids = item_ids if item_ids is not None else list(self._items)
            targets = [self._items[i] for i in ids if i in self._items and self._items[i].doc is not None]
        results = {}
        for item in targets:
            try:
                result = self._anonymize(item.doc, options or {}, item)
            except Exception as exc:  # pragma: no cover
                log_exception(log, "Error re-anonimizando el elemento %s", exc, item.id)
                results[item.id] = _error("process_error", str(exc))
                continue
            with self._lock:
                item.result = result
            results[item.id] = result
        if not results and item_ids:
            return _error("no_document")
        return {"ok": True, "results": results}

    # ------------------------------------------------------------------ exportación
    def _content(self, document: dict, fmt: str, options: dict | None) -> tuple[str, dict]:
        """Texto y metadatos a exportar.

        Si el usuario no editó el resultado, se regenera en el formato más adecuado:
        texto plano para .txt y Markdown (estructura de títulos, listas y tablas) para .docx.
        Si lo editó, se respeta su versión tal cual.
        """
        text = document.get("text", "")
        meta = dict(document.get("meta") or {})
        if document.get("edited"):
            return text, meta
        want = {"txt": "text", "docx": "markdown"}.get(fmt)
        with self._lock:
            item = self._items.get(document.get("id") or "")
        if want and item is not None and item.doc is not None and meta.get("format") != want:
            result = anonymize_document(item.doc, {**(options or {}), "output_format": want})
            return result["text"], {**meta, **result}
        return text, meta

    def export_file(self, document: dict, fmt: str = "md", options: dict | None = None) -> dict:
        """Guarda un resultado. `document`: {"id", "name", "text", "edited", "meta"}."""
        if fmt not in FORMATS:
            return _error("unsupported_format", fmt)
        if self._window is None:
            return _error("no_window")
        label, ext = FORMATS[fmt]
        result = self._window.create_file_dialog(
            _dialog_type("SAVE"),
            save_filename=f"{safe_stem(document.get('name'))}_anonimizado{ext}",
            file_types=(f"{label} (*{ext})",),
        )
        if not result:
            return {"ok": False, "cancelled": True}
        target = Path(result[0] if isinstance(result, (list, tuple)) else str(result))
        if target.suffix.lower() != ext:
            target = target.with_name(target.name + ext)
        text, meta = self._content(document, fmt, options)
        meta.setdefault("name", document.get("name"))
        return self._write(target, fmt, text, meta)

    def export_batch(self, documents: list[dict], fmt: str = "md", options: dict | None = None,
                     generic_names: bool = False) -> dict:
        """Exporta varios resultados a una carpeta elegida por el usuario."""
        if fmt not in FORMATS:
            return _error("unsupported_format", fmt)
        if self._window is None:
            return _error("no_window")
        folder = self._window.create_file_dialog(_dialog_type("FOLDER"))
        if not folder:
            return {"ok": False, "cancelled": True}
        folder_path = Path(folder[0] if isinstance(folder, (list, tuple)) else str(folder))
        return self.export_to_folder(str(folder_path), documents, fmt, options, generic_names)

    def export_to_folder(self, folder: str, documents: list[dict], fmt: str,
                         options: dict | None = None, generic_names: bool = False) -> dict:
        if fmt not in FORMATS:
            return _error("unsupported_format", fmt)
        folder_path = Path(folder)
        _, ext = FORMATS[fmt]
        written: list[str] = []
        used: set[str] = set()
        for index, document in enumerate(documents or [], start=1):
            # Los nombres originales suelen incluir el nombre del paciente: opción genérica.
            stem = f"documento_{index:02d}" if generic_names else safe_stem(document.get("name"))
            stem = f"{stem}_anonimizado"
            candidate, n = stem, 2
            while candidate.lower() in used or (folder_path / f"{candidate}{ext}").exists():
                candidate, n = f"{stem}_{n}", n + 1
            used.add(candidate.lower())
            text, meta = self._content(document, fmt, options)
            meta["name"] = f"{candidate}{ext}" if generic_names else document.get("name")
            res = self._write(folder_path / f"{candidate}{ext}", fmt, text, meta)
            if not res.get("ok"):
                return {**res, "written": written}
            written.append(res["path"])
        return {"ok": True, "folder": str(folder_path), "count": len(written), "written": written}

    @staticmethod
    def _write(target: Path, fmt: str, content: str, meta: dict | None) -> dict:
        try:
            target.write_bytes(export_bytes(fmt, content, meta))
        except ImportError as exc:
            return _error("missing_dependency", str(exc))
        except OSError as exc:
            return _error("write_error", str(exc))
        return {"ok": True, "path": str(target)}

    def copy_to_clipboard(self, text: str) -> dict:
        try:
            import pyperclip

            pyperclip.copy(text)
            return {"ok": True}
        except Exception as exc:
            return _error("clipboard_error", str(exc))
