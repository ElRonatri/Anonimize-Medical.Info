"""API expuesta a la interfaz React a través de `window.pywebview.api`.

El trabajo pesado (lectura de PDF y OCR) se ejecuta en un hilo secundario que consume una
cola de lotes; la interfaz consulta el avance con `get_job` sin bloquearse. Re-anonimizar
con otras opciones usa los documentos ya extraídos en memoria y toma milisegundos.
"""

from __future__ import annotations

import base64
import logging
import os
import queue
import re
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anonymizer import ExtractionError, __version__, anonymize_document, identifiers, load_text, ner, ocr, parallel
from anonymizer.document import Document
from anonymizer.exporters import FORMATS, export_bytes
from anonymizer.privacy import log_exception
from appdata import PrefStore

# Respuestas y argumentos JSON intercambiados con la interfaz (PyWebView).
JSONDict = dict[str, Any]

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 80 * 1024 * 1024  # 80 MB por archivo
# Arrancar procesos cuesta ~0,2-0,4 s; con PDFs de texto livianos (KB) el lote entero tarda menos.
# Se usa paralelo con OCR forzado, con lotes grandes (los escaneos pesan cientos de KB por página)
# o si los procesos ya están activos. Medición en docs/benchmarks.md.
PARALLEL_MIN_BYTES = 1024 * 1024


def _dialog_type(name: str) -> Any:
    """Compatibilidad entre pywebview 4.x (OPEN_DIALOG) y 5.x+ (FileDialog.OPEN)."""
    import webview

    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None:
        return getattr(file_dialog, name)
    return getattr(webview, f"{name}_DIALOG")


def _file_size(path: str | None) -> int:
    try:
        return max(1, os.path.getsize(path)) if path else 1
    except OSError:
        return 1


def _eta(job: Job, items: list[Any]) -> float | None:
    """Segundos restantes estimados, ponderando cada archivo por su tamaño."""
    if job.started is None or not items:
        return None
    elapsed = time.monotonic() - job.started
    total = sum(i.size for i in items)
    done = sum(i.size * i.fraction() for i in items)
    if elapsed < 1.0 or done <= 0 or total <= 0:
        return None
    return round(float(elapsed * (total - done) / done), 1)


def _error(code: str, detail: str = "") -> JSONDict:
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
    result: JSONDict | None = None
    size: int = 1  # bytes (peso para el tiempo estimado)
    worker: int | None = None  # pid del proceso que lo extrajo

    def public(self) -> JSONDict:
        return {"id": self.id, "name": self.name, "status": self.status, "stage": self.stage,
                "page": self.page, "pages": self.pages, "error": self.error, "detail": self.detail,
                "worker": self.worker}

    def fraction(self) -> float:
        if self.status in ("done", "error", "cancelled"):
            return 1.0
        if self.status == "processing" and self.pages:
            return 0.95 * min(self.page, self.pages) / self.pages
        return 0.0


@dataclass
class Job:
    id: str
    item_ids: list[str]
    options: JSONDict
    num: int = 0  # número para la cancelación compartida con los procesos
    workers: int = 1
    mode: str = "sequential"  # sequential | parallel
    cancelled: bool = False
    done: bool = False
    current: str | None = None
    started: float | None = None
    finished: set[str] = field(default_factory=set)


class Api:
    def __init__(self, prefs: PrefStore | None = None) -> None:
        self._prefs = prefs or PrefStore()
        self._window: Any | None = None  # webview.Window; privado: pywebview no expone atributos que empiezan con "_"
        self._lock = threading.RLock()
        self._items: dict[str, Item] = {}
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._pool: parallel.ExtractionPool | None = None
        self._job_counter = 0

    def _set_window(self, window: Any) -> None:  # webview.Window
        self._window = window

    # ------------------------------------------------------------------ preferencias
    def get_prefs(self) -> JSONDict:
        """Preferencias guardadas (sólo claves y tipos permitidos; ver appdata.PREF_RULES)."""
        return {"ok": True, "prefs": self._prefs.load()}

    def set_pref(self, key: str, value: Any) -> JSONDict:
        try:
            saved = self._prefs.set(str(key), value)
        except OSError as exc:
            log_exception(log, "No se pudo guardar una preferencia", exc)
            return _error("write_error")
        return {"ok": saved} if saved else _error("invalid_pref")

    # ------------------------------------------------------------------ info
    def get_app_info(self) -> JSONDict:
        return {
            "version": __version__,
            "ocr": ocr.info(),
            "ocr_available": ocr.available(),
            "regions": {k: list(v) for k, v in identifiers.REGIONES.items()},
            "country_formats": identifiers.formatos_por_pais(),
            "export_formats": list(FORMATS),
            "ner": ner.info(),
            "cpu_count": parallel.cpu_count(),
            "default_workers": parallel.default_workers(),
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
    def start_batch(self, files: list[JSONDict], options: JSONDict | None = None) -> JSONDict:
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
            item.size = len(item.data) if item.data is not None else _file_size(item.path)
            items.append(item)
            if item.status == "error":
                rejected.append(item.id)
        with self._lock:
            for item in items:
                self._items[item.id] = item
        job = self._enqueue([i.id for i in items if i.id not in rejected], options)
        return {"ok": True, "job_id": job.id, "items": [i.public() for i in items]}

    def reload_items(self, item_ids: list[str], options: JSONDict | None = None) -> JSONDict:
        """Vuelve a extraer (p. ej. tras cambiar el modo de OCR) documentos ya cargados."""
        with self._lock:
            ids = [i for i in item_ids or [] if i in self._items
                   and (self._items[i].path or self._items[i].data)]
            for i in ids:
                item = self._items[i]
                item.status, item.stage, item.page, item.error, item.detail = "queued", "", 0, "", ""
        job = self._enqueue(ids, options)
        return {"ok": True, "job_id": job.id, "items": [self._items[i].public() for i in ids]}

    def _enqueue(self, ids: list[str], options: JSONDict | None) -> Job:
        opts = dict(options or {})
        with self._lock:
            self._job_counter += 1
            num = self._job_counter
        job = Job(id=uuid.uuid4().hex[:12], item_ids=ids, options=opts, num=num,
                  workers=parallel.resolve_workers(opts.get("max_workers")))
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

    def get_job(self, job_id: str, known: list[str] | None = None) -> JSONDict:
        """Estado del lote. Incluye el resultado de cada archivo terminado sólo una vez."""
        known_set = set(known or [])
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return _error("no_job")
            items = [self._items[i] for i in job.item_ids if i in self._items]
            results = {i.id: i.result for i in items
                       if i.status == "done" and i.result and i.id not in known_set}
            active = [i.id for i in items if i.status == "processing"]
            return {
                "ok": True,
                "done": job.done,
                "cancelled": job.cancelled,
                "current": job.current or (active[0] if active else None),
                "active": active,
                "workers": job.workers,
                "mode": job.mode,
                "total": len(items),
                "completed": sum(1 for i in items if i.status in ("done", "error", "cancelled")),
                "eta_seconds": None if job.done else _eta(job, items),
                "items": [i.public() for i in items],
                "results": results,
            }

    def cancel_job(self, job_id: str) -> JSONDict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return _error("no_job")
            job.cancelled = True
            pool = self._pool
        if pool is not None:
            pool.cancel_job(job.num)  # los procesos lo ven en la siguiente página
        return {"ok": True}

    def shutdown(self) -> None:
        """Detiene los procesos de extracción (al cerrar la aplicación)."""
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown()

    def remove_items(self, item_ids: list[str]) -> JSONDict:
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
            job.started = time.monotonic()
            pending = [i for i in job.item_ids if i in self._items]
            try:
                if self._use_parallel(job, pending):
                    job.mode = "parallel"
                    self._run_parallel(job, pending)
                else:
                    self._run_sequential(job, pending)
            except Exception as exc:  # pragma: no cover - p. ej. no se pudo crear el pool
                log_exception(log, "Error en el lote %s", exc, job.id)
                with self._lock:
                    for item_id in pending:
                        item = self._items.get(item_id)
                        if item is not None and item.status in ("queued", "processing"):
                            item.status, item.error = "error", "process_error"
            with self._lock:
                job.current = None
                job.done = True

    # ---------------------------------------------------------------- modo secuencial (1 proceso)
    def _run_sequential(self, job: Job, ids: list[str]) -> None:
        opts = job.options
        for item_id in ids:
            with self._lock:
                maybe = self._items.get(item_id)
                if maybe is None:
                    continue
                item = maybe
                if job.cancelled:
                    item.status = "cancelled"
                    continue
                job.current = item_id
                item.status, item.stage, item.page, item.worker = "processing", "text", 0, os.getpid()

            def progress(page: int, total: int, stage: str, item: Item = item) -> None:
                if job.cancelled:
                    raise parallel.Cancelled  # se abandona el documento en la página actual
                with self._lock:
                    item.page, item.pages, item.stage = page, total, stage

            try:
                if item.data is None and item.path:
                    item.data = parallel.read_source(item.path, None)
                doc = parallel.extract_in_thread(item.name, item.path, item.data, opts.get("ocr_mode", "auto"),
                                                 opts.get("ocr_engine", "auto"), progress)
            except parallel.Cancelled:
                with self._lock:
                    item.status = "cancelled"
                continue
            except ExtractionError as exc:
                self._fail(item, str(exc))
                continue
            except Exception as exc:  # pragma: no cover - errores inesperados
                log_exception(log, "Error procesando el elemento %s", exc, item.id)
                self._fail(item, "process_error")
                continue
            self._finish(item, doc, opts)

    # ---------------------------------------------------------------- modo paralelo (procesos)
    def _ensure_pool(self, workers: int) -> parallel.ExtractionPool:
        with self._lock:
            pool = self._pool
        if pool is not None and pool.workers != workers:
            pool.shutdown()  # entre lotes el pool está libre: se ajusta al nuevo tamaño
            pool = None
        if pool is None:
            pool = parallel.ExtractionPool(workers, self._on_worker_progress)
            with self._lock:
                self._pool = pool
        return pool

    def _on_worker_progress(self, item_id: str, page: int, total: int, stage: str) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item is None or item.status not in ("queued", "processing"):
                return
            item.status = "processing"  # un proceso lo tomó (respeta el orden de la cola)
            item.page, item.stage = page, stage
            if total:
                item.pages = total

    def _use_parallel(self, job: Job, ids: list[str]) -> bool:
        if job.workers <= 1 or len(ids) <= 1:
            return False
        with self._lock:
            warm = self._pool is not None and self._pool.workers == job.workers
            total = sum(self._items[i].size for i in ids if i in self._items)
        forced = job.options.get("parallel") == "force"  # diagnóstico (autoprueba del .exe)
        return forced or warm or job.options.get("ocr_mode") == "force" or total >= PARALLEL_MIN_BYTES

    def _discard_pool(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            try:
                pool.shutdown()
            except Exception as exc:  # pragma: no cover - pool ya roto
                log_exception(log, "Error cerrando un pool roto", exc)

    def _run_parallel(self, job: Job, ids: list[str]) -> None:
        opts = job.options
        futures: dict[Future[Any], Item] = {}
        try:
            pool = self._ensure_pool(job.workers)
            for item_id in ids:  # se envían en el orden de la cola
                with self._lock:
                    maybe = self._items.get(item_id)
                    if maybe is None:
                        continue
                    item = maybe
                    item.status, item.stage, item.page = "queued", "", 0
                future = pool.submit(item.id, job.num, item.name, item.path if item.data is None else None,
                                     item.data, opts.get("ocr_mode", "auto"), opts.get("ocr_engine", "auto"))
                futures[future] = item
        except (BrokenProcessPool, OSError) as exc:
            # Los procesos no pudieron arrancar: el lote se procesa en modo secuencial.
            log_exception(log, "Pool de procesos no disponible; se usa modo secuencial", exc)
            self._discard_pool()
            for future in futures:
                future.cancel()
            self._run_sequential(job, ids)
            return

        cancel_sent = False
        retry: list[str] = []
        remaining = set(futures)
        while remaining:
            done, remaining = wait(remaining, timeout=0.2, return_when=FIRST_COMPLETED)
            if job.cancelled and not cancel_sent:
                cancel_sent = True
                pool.cancel_job(job.num)
                for future in remaining:
                    future.cancel()  # los que aún no empezaron no llegan a ejecutarse
            for future in done:
                if not self._collect(futures[future], future, opts):
                    retry.append(futures[future].id)
        if retry:
            # Un proceso murió (p. ej. memoria insuficiente): el pool queda inservible. Se descarta
            # (el próximo lote crea uno nuevo) y los archivos afectados se reprocesan aquí mismo.
            self._discard_pool()
            self._run_sequential(job, retry)

    def _collect(self, item: Item, future: Future[Any], opts: JSONDict) -> bool:
        """Registra el resultado de un proceso. False si el pool se rompió (hay que reintentar)."""
        if future.cancelled():
            with self._lock:
                item.status = "cancelled"
            return True
        try:
            state, payload, pid = future.result()
        except BrokenProcessPool as exc:
            log_exception(log, "Un proceso de extracción terminó inesperadamente (%s)", exc, item.id)
            return False
        except Exception as exc:  # pragma: no cover - error inesperado del proceso
            log_exception(log, "Error en un proceso de extracción (%s)", exc, item.id)
            self._fail(item, "process_error")
            return True
        with self._lock:
            item.worker = pid
        if state == "ok":
            self._finish(item, payload, opts)
        elif state == "cancelled":
            with self._lock:
                item.status = "cancelled"
        else:
            self._fail(item, payload)
        return True

    # ---------------------------------------------------------------- resultados
    def _finish(self, item: Item, doc: Document, opts: JSONDict) -> None:
        with self._lock:
            item.stage = "anonymize"
        try:
            result = self._anonymize(doc, opts, item)
        except Exception as exc:  # pragma: no cover - errores inesperados
            log_exception(log, "Error procesando el elemento %s", exc, item.id)
            self._fail(item, "process_error")
            return
        with self._lock:
            item.doc, item.result, item.status, item.pages = doc, result, "done", result["pages"]

    def _fail(self, item: Item, code: str) -> None:
        with self._lock:
            item.status, item.error, item.detail = "error", code.split(":", 1)[0], code

    @staticmethod
    def _anonymize(doc: Document, options: JSONDict, item: Item) -> JSONDict:
        result = anonymize_document(doc, options)
        result["ok"] = True
        result["id"] = item.id
        result["file_name"] = item.name
        return result

    # ------------------------------------------------------------------ texto pegado
    def process_text(self, text: str, options: JSONDict | None = None) -> JSONDict:
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
    def reprocess(self, options: JSONDict | None = None, item_ids: list[str] | None = None) -> JSONDict:
        """Re-anonimiza documentos ya extraídos con nuevas opciones (sin releer los PDF)."""
        with self._lock:
            ids = item_ids if item_ids is not None else list(self._items)
            targets = [(self._items[i], self._items[i].doc) for i in ids if i in self._items]
        results = {}
        for item, doc in targets:
            if doc is None:
                continue
            try:
                result = self._anonymize(doc, options or {}, item)
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
    def _content(self, document: JSONDict, fmt: str, options: JSONDict | None) -> tuple[str, JSONDict]:
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

    def export_file(self, document: JSONDict, fmt: str = "md", options: JSONDict | None = None) -> JSONDict:
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

    def export_batch(self, documents: list[JSONDict], fmt: str = "md", options: JSONDict | None = None,
                     generic_names: bool = False) -> JSONDict:
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

    def export_to_folder(self, folder: str, documents: list[JSONDict], fmt: str,
                         options: JSONDict | None = None, generic_names: bool = False) -> JSONDict:
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
    def _write(target: Path, fmt: str, content: str, meta: JSONDict | None) -> JSONDict:
        try:
            target.write_bytes(export_bytes(fmt, content, meta))
        except ImportError as exc:
            return _error("missing_dependency", str(exc))
        except OSError as exc:
            return _error("write_error", str(exc))
        return {"ok": True, "path": str(target)}

    def copy_to_clipboard(self, text: str) -> JSONDict:
        try:
            import pyperclip

            pyperclip.copy(text)
            return {"ok": True}
        except Exception as exc:
            return _error("clipboard_error", str(exc))
