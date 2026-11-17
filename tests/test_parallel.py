"""Bloque 4: extracción en paralelo, orden de la cola, cancelación y tiempo estimado."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from anonymizer import ocr, parallel
from api import Api

HAS_TESSERACT = ocr.TESSERACT in ocr.available_engines()


@pytest.fixture
def api(monkeypatch):
    import api as api_module

    monkeypatch.setattr(api_module, "PARALLEL_MIN_BYTES", 0)  # PDFs de prueba pequeños: forzar paralelo
    instance = Api()
    yield instance
    instance.shutdown()


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    pytest.importorskip("reportlab")
    import make_samples

    folder = tmp_path_factory.mktemp("pdfs")
    paths = []
    for n in range(4):
        path = folder / f"epicrisis_{n}.pdf"
        make_samples.epicrisis_es(path)
        paths.append(path)
    return paths


@pytest.fixture(scope="module")
def scanned(pdfs, tmp_path_factory):
    """PDF escaneado de 3 páginas: con OCR forzado cada documento tarda ~1-3 s."""
    import pdfplumber

    with pdfplumber.open(pdfs[0]) as pdf:
        images = [p.to_image(resolution=110).original.convert("RGB") for p in pdf.pages]
    images.append(images[0])
    path = tmp_path_factory.mktemp("scan") / "escaneado.pdf"
    images[0].save(path, save_all=True, append_images=images[1:])
    return path


def run_job(api, job_id, on_state=None, timeout=180):
    deadline = time.monotonic() + timeout
    results = {}
    while time.monotonic() < deadline:
        state = api.get_job(job_id, list(results))
        results.update(state["results"])
        if on_state:
            on_state(state)
        if state["done"]:
            return state, results
        time.sleep(0.05)
    raise TimeoutError


# --------------------------------------------------------------------------- configuración

def test_resolve_workers():
    default = parallel.default_workers()
    assert 1 <= default <= 4 and default <= max(1, parallel.cpu_count() - 1)
    for value in (None, "", "auto", 0, "0", "x"):
        assert parallel.resolve_workers(value) == default
    assert parallel.resolve_workers("1") == 1
    assert parallel.resolve_workers(-3) == 1
    assert parallel.resolve_workers(10_000) == parallel.cpu_count()


def test_app_info_reports_workers(api):
    info = api.get_app_info()
    assert info["cpu_count"] >= 1 and info["default_workers"] == parallel.default_workers()


# --------------------------------------------------------------------------- paridad y procesos

def test_parallel_and_sequential_give_identical_results(api, pdfs):
    files = [{"path": str(p)} for p in pdfs]
    par_state, par = run_job(api, api.start_batch(files, {"max_workers": 3})["job_id"])
    seq_state, seq = run_job(api, api.start_batch(files, {"max_workers": 1})["job_id"])
    assert par_state["workers"] == 3 and seq_state["workers"] == 1
    assert par_state["mode"] == "parallel" and seq_state["mode"] == "sequential"
    assert sorted(r["text"] for r in par.values()) == sorted(r["text"] for r in seq.values())
    assert all(i["worker"] != os.getpid() for i in par_state["items"])  # extraídos en procesos hijos
    assert all(i["worker"] == os.getpid() for i in seq_state["items"])  # en el hilo de trabajo


def test_worker_processes_have_network_blocked(api, pdfs):
    pool = api._ensure_pool(2)
    assert pool._executor.submit(parallel.worker_network_blocked).result(timeout=60) is True


def test_errors_in_workers_are_reported(api, pdfs, tmp_path):
    broken = tmp_path / "roto.pdf"
    broken.write_bytes(b"%PDF-1.4 no es un pdf")
    files = [{"path": str(pdfs[0])}, {"path": str(broken)}, {"path": str(tmp_path / "no_existe.pdf")}]
    state, _ = run_job(api, api.start_batch(files, {"max_workers": 2})["job_id"])
    errors = {i["name"]: (i["status"], i["error"]) for i in state["items"]}
    assert errors["epicrisis_0.pdf"][0] == "done"
    assert errors["roto.pdf"] == ("error", "invalid_pdf")
    assert errors["no_existe.pdf"] == ("error", "file_not_found")


# --------------------------------------------------------------------------- concurrencia real (OCR)

@pytest.mark.skipif(not HAS_TESSERACT, reason="requiere Tesseract para generar trabajo lento")
def test_runs_concurrently_in_queue_order_with_eta(api, scanned):
    files = [{"path": str(scanned)} for _ in range(5)]
    job = api.start_batch(files, {"max_workers": 2, "ocr_mode": "force", "ocr_engine": "tesseract"})
    order = [i["id"] for i in job["items"]]
    max_active, etas, violations = 0, [], []

    def observe(state):
        nonlocal max_active
        status = {i["id"]: i["status"] for i in state["items"]}
        stage = {i["id"]: i["stage"] for i in state["items"]}
        # Extracciones en curso (la anonimización final ocurre en el proceso principal).
        active = [i for i in order if status[i] == "processing" and stage[i] != "anonymize"]
        max_active = max(max_active, len(active))
        if state["eta_seconds"] is not None:
            etas.append(state["eta_seconds"])
        # FIFO: ningún archivo empieza mientras otro anterior en la cola sigue esperando.
        for k, item_id in enumerate(order):
            if status[item_id] != "queued" and any(status[j] == "queued" for j in order[:k]):
                violations.append(item_id)

    state, results = run_job(api, job["job_id"], observe)
    assert len(results) == 5 and all(i["status"] == "done" for i in state["items"])
    assert max_active == 2  # nunca más que el límite configurado, y sí en paralelo
    assert violations == []
    assert etas and all(e >= 0 for e in etas)
    assert state["eta_seconds"] is None  # terminado
    assert len({i["worker"] for i in state["items"]}) == 2


@pytest.mark.skipif(not HAS_TESSERACT, reason="requiere Tesseract para generar trabajo lento")
@pytest.mark.parametrize("workers", [1, 2])
def test_cancel_stops_running_documents_midway(api, scanned, workers):
    files = [{"path": str(scanned)} for _ in range(4)]
    job = api.start_batch(files, {"max_workers": workers, "ocr_mode": "force", "ocr_engine": "tesseract"})
    cancelled_at = {}

    def observe(state):
        running = [i for i in state["items"] if i["status"] == "processing" and i["stage"] == "ocr"]
        if running and not cancelled_at:
            cancelled_at["t"] = time.monotonic()
            assert api.cancel_job(job["job_id"])["ok"]

    state, results = run_job(api, job["job_id"], observe)
    elapsed = time.monotonic() - cancelled_at["t"]
    statuses = [i["status"] for i in state["items"]]
    assert state["cancelled"] and "processing" not in statuses and "queued" not in statuses
    assert statuses.count("cancelled") >= 4 - workers  # los que no empezaron nunca se procesan
    assert len(results) < 4
    # Un documento en curso se abandona en la siguiente página: mucho antes que terminar el lote.
    assert elapsed < 8, f"la cancelación tardó {elapsed:.1f} s"


def test_shutdown_is_idempotent(api):
    api._ensure_pool(2)
    api.shutdown()
    api.shutdown()
    assert api._pool is None


def test_pool_resizes_between_jobs(api, pdfs):
    files = [{"path": str(p)} for p in pdfs[:2]]
    run_job(api, api.start_batch(files, {"max_workers": 2})["job_id"])
    first = api._pool
    run_job(api, api.start_batch(files, {"max_workers": 3})["job_id"])
    assert api._pool is not first and api._pool.workers == 3


def test_parallel_module_has_no_window_imports():
    source = Path(parallel.__file__).read_text(encoding="utf-8")
    assert "webview" not in source  # los hijos no deben importar la interfaz


def test_small_text_batches_stay_sequential(pdfs):
    """Sin el umbral forzado: PDFs de texto livianos no pagan el arranque de procesos."""
    api = Api()
    try:
        state, results = run_job(api, api.start_batch([{"path": str(p)} for p in pdfs], {"max_workers": 3})["job_id"])
        assert state["mode"] == "sequential" and len(results) == len(pdfs)
        assert api._pool is None
        forced = api.start_batch([{"path": str(p)} for p in pdfs[:2]], {"max_workers": 2, "ocr_mode": "force"})
        assert run_job(api, forced["job_id"])[0]["mode"] == "parallel"  # OCR forzado: vale la pena
    finally:
        api.shutdown()


def test_pool_that_cannot_start_falls_back_to_sequential(api, pdfs, monkeypatch):
    from concurrent.futures.process import BrokenProcessPool

    class BrokenPool:
        workers = 2

        def submit(self, *a, **k):
            raise BrokenProcessPool("no se pudo crear el proceso")

        def shutdown(self):
            pass

    monkeypatch.setattr(api, "_ensure_pool", lambda workers: BrokenPool())
    state, results = run_job(api, api.start_batch([{"path": str(p)} for p in pdfs], {"max_workers": 2})["job_id"])
    assert len(results) == len(pdfs) and all(i["status"] == "done" for i in state["items"])
    assert all(i["worker"] == os.getpid() for i in state["items"])  # reprocesados en secuencial


@pytest.mark.skipif(not HAS_TESSERACT, reason="requiere Tesseract para generar trabajo lento")
def test_killed_worker_is_recovered(api, scanned):
    """Si un proceso muere (p. ej. sin memoria), sus archivos se reprocesan y el pool se recrea."""
    import signal

    files = [{"path": str(scanned)} for _ in range(3)]
    job = api.start_batch(files, {"max_workers": 2, "ocr_mode": "force", "ocr_engine": "tesseract"})
    killed = {}

    def observe(state):
        busy = [i for i in state["items"] if i["status"] == "processing" and i["stage"] == "ocr"]
        if busy and not killed:
            pids = list(api._pool._executor._processes)
            killed["pid"] = pids[0]
            os.kill(pids[0], signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)

    state, results = run_job(api, job["job_id"], observe)
    assert killed and len(results) == 3 and all(i["status"] == "done" for i in state["items"])
    assert api._pool is None  # descartado; el próximo lote crea uno nuevo
    second = run_job(api, api.start_batch(files[:2], {"max_workers": 2})["job_id"])[0]
    assert all(i["status"] == "done" for i in second["items"])


ORPHAN_SCRIPT = r"""
import multiprocessing as mp, os, sys, time
sys.path.insert(0, sys.argv[1])
from anonymizer.parallel import watch_parent

def child():
    watch_parent()
    time.sleep(120)

def parent(q):
    c = mp.get_context("spawn").Process(target=child)
    c.start()
    q.put(c.pid)
    time.sleep(1.5)  # el hijo ya está vigilando
    os._exit(3)      # cierre abrupto: sin cerrar el pool ni esperar a los hijos

def alive(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            return "\nState:\tZ" not in f.read()
    except FileNotFoundError:
        return False

if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=parent, args=(q,))
    p.start()
    pid = q.get(timeout=60)
    p.join(60)
    for _ in range(100):
        if not alive(pid):
            print("child-exited")
            break
        time.sleep(0.1)
    else:
        print("child-alive")
        os.kill(pid, 9)
"""


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="usa /proc para ver el estado del hijo")
def test_workers_exit_when_main_process_dies(tmp_path):
    """Sin la vigilancia, un hijo de extracción quedaba vivo (con documentos en memoria) tras un fallo."""
    script = tmp_path / "orphan.py"
    script.write_text(ORPHAN_SCRIPT, encoding="utf-8")
    backend = Path(__file__).resolve().parent.parent / "backend"
    out = subprocess.run([sys.executable, str(script), str(backend)], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "child-exited", out.stdout + out.stderr


def test_watch_parent_is_noop_in_main_process():
    assert parallel.watch_parent() is None
