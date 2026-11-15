"""Extracción de documentos (PDF + OCR) en paralelo con procesos.

La lectura de PDF (pdfminer, Python puro) y el OCR consumen CPU: con hilos el GIL los
serializa, con procesos escalan con los núcleos. Sólo la EXTRACCIÓN corre en los procesos
hijos; cada uno devuelve el `Document` (estructura simple, se serializa con pickle) y la
anonimización —que toma milisegundos y necesita el estado de la sesión— sigue en el proceso
principal.

* Contexto "spawn" (el único en Windows): los hijos arrancan limpios e importan sólo lo
  necesario. En el ejecutable de PyInstaller requiere `multiprocessing.freeze_support()`.
* Cada hijo activa el bloqueo de red y el logging sin contenido clínico (no se heredan).
* Progreso por página: cola compartida -> hilo oyente en el proceso principal.
* Cancelación: arreglo compartido con los números de lote cancelados; el hijo lo revisa en
  cada página y abandona el documento sin esperar a terminarlo.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .document import Document
from .extract import ExtractionError, load_bytes
from .privacy import log_exception

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 80 * 1024 * 1024
_CANCEL_SLOTS = 64

ProgressCallback = Callable[[str, int, int, str], None]  # (item_id, página, total, etapa)


def cpu_count() -> int:
    return os.cpu_count() or 1


def default_workers() -> int:
    """min(4, núcleos - 1): deja un núcleo libre para la interfaz y limita la memoria
    (cada proceso con RapidOCR carga ~150 MB de modelos)."""
    return max(1, min(4, cpu_count() - 1))


def resolve_workers(requested: Any) -> int:
    if requested in (None, "", "auto", 0, "0"):
        return default_workers()
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return default_workers()
    return max(1, min(value, cpu_count()))


class Cancelled(Exception):
    """El lote se canceló mientras se procesaba el documento."""


# --------------------------------------------------------------------------- lado del proceso hijo

_progress_queue: Any = None
_cancelled: Any = None


def _init_worker(progress_queue: Any, cancelled: Any, ocr_threads: int) -> None:
    global _progress_queue, _cancelled
    _progress_queue, _cancelled = progress_queue, cancelled
    from . import ocr
    from .privacy import block_network, configure_logging

    configure_logging(dev=False)
    block_network()  # los hijos también tienen prohibido conectarse a internet
    # Repartir los núcleos: N procesos con OCR multihilo sin límite se estorban entre sí
    # (medido: Tesseract pasa de ~1 s a más de 180 s por página con 2 procesos).
    ocr.set_thread_limit(ocr_threads)


def ocr_threads_per_worker(workers: int) -> int:
    return max(1, cpu_count() // max(1, workers))


def _is_cancelled(job_num: int) -> bool:
    return _cancelled is not None and job_num in _cancelled[:]


def read_source(path: str | None, data: bytes | None) -> bytes:
    if data is not None:
        return data
    if not path:
        raise ExtractionError("file_not_found")
    source = Path(path)
    if not source.is_file():
        raise ExtractionError("file_not_found")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ExtractionError("file_too_large")
    return source.read_bytes()


def extract_task(item_id: str, job_num: int, name: str, path: str | None, data: bytes | None,
                 ocr_mode: str, ocr_engine: str) -> tuple[str, Any, int]:
    """Se ejecuta en un proceso hijo. Devuelve (estado, documento o código de error, pid)."""
    pid = os.getpid()

    def progress(page: int, total: int, stage: str) -> None:
        if _is_cancelled(job_num):
            raise Cancelled
        if _progress_queue is not None:
            _progress_queue.put((item_id, page, total, stage))

    try:
        progress(0, 0, "text")
        doc = load_bytes(name, read_source(path, data), ocr_mode=ocr_mode, ocr_engine=ocr_engine,
                         progress=progress)
        return "ok", doc, pid
    except Cancelled:
        return "cancelled", None, pid
    except ExtractionError as exc:
        return "error", str(exc), pid
    except Exception as exc:  # pragma: no cover - errores inesperados en el hijo
        log_exception(log, "Error extrayendo el elemento %s", exc, item_id)
        return "error", f"process_error:{type(exc).__name__}", pid


# --------------------------------------------------------------------------- lado del proceso principal

class ExtractionPool:
    """Pool de procesos de extracción con progreso y cancelación por lote."""

    def __init__(self, workers: int, on_progress: ProgressCallback) -> None:
        self.workers = workers
        ctx = mp.get_context("spawn")
        self._progress: Any = ctx.Queue()
        self._cancelled: Any = ctx.Array("i", _CANCEL_SLOTS)
        self._cancel_index = 0
        self._executor = ProcessPoolExecutor(max_workers=workers, mp_context=ctx,
                                             initializer=_init_worker,
                                             initargs=(self._progress, self._cancelled,
                                                       ocr_threads_per_worker(workers)))
        self._on_progress = on_progress
        self._listener = threading.Thread(target=self._listen, name="extraction-progress", daemon=True)
        self._listener.start()

    def _listen(self) -> None:
        while True:
            try:
                message = self._progress.get()
            except (EOFError, OSError):  # pragma: no cover - la cola se cerró
                return
            if message is None:
                return
            try:
                self._on_progress(*message)
            except Exception as exc:  # pragma: no cover
                log_exception(log, "Error actualizando el progreso", exc)

    def submit(self, item_id: str, job_num: int, name: str, path: str | None, data: bytes | None,
               ocr_mode: str, ocr_engine: str) -> Future:
        return self._executor.submit(extract_task, item_id, job_num, name, path, data, ocr_mode, ocr_engine)

    def cancel_job(self, job_num: int) -> None:
        with self._cancelled.get_lock():
            self._cancelled[self._cancel_index % _CANCEL_SLOTS] = job_num
            self._cancel_index += 1

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        try:
            self._progress.put(None)
        except (OSError, ValueError):  # pragma: no cover
            pass
        self._listener.join(timeout=2)


def extract_in_thread(name: str, path: str | None, data: bytes | None, ocr_mode: str, ocr_engine: str,
                      progress: Callable[[int, int, str], None]) -> Document:
    """Modo secuencial (1 proceso): misma extracción en el hilo de trabajo."""
    return load_bytes(name, read_source(path, data), ocr_mode=ocr_mode, ocr_engine=ocr_engine,
                      progress=progress)


def worker_network_blocked() -> bool:
    """Diagnóstico (autoprueba y tests): ¿el proceso hijo tiene la red bloqueada?"""
    from .privacy import network_blocked

    return network_blocked()
