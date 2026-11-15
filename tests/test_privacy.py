"""Garantías de privacidad operativa (ver anonymizer/privacy.py y la sección del README)."""

from __future__ import annotations

import base64
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import main
from anonymizer import extract, load_bytes, ocr
from anonymizer.privacy import QUIET_LOGGERS, configure_logging, exception_summary, log_exception
from api import Api

# Valores ficticios que NUNCA deben aparecer en los logs.
SECRET_NAME = "Wenceslao Zubizarreta"
SECRET_ID = "16.789.012-3"
SECRET_FILE = "Epicrisis Wenceslao Zubizarreta.txt"
DOC = f"Nombre: {SECRET_NAME}\nRUT: {SECRET_ID}\nEl Sr. Zubizarreta refiere dolor.\n"
SECRETS = ("Wenceslao", "Zubizarreta", SECRET_ID, "16789012")


def all_log_text(caplog) -> str:
    parts = []
    for record in caplog.records:
        parts.append(record.getMessage())
        if record.exc_text:
            parts.append(record.exc_text)
        if record.exc_info:
            parts.append(logging.Formatter().formatException(record.exc_info))
    return "\n".join(parts)


def wait(api, job_id):
    for _ in range(400):
        state = api.get_job(job_id, [])
        if state["done"]:
            return state
        time.sleep(0.02)
    raise TimeoutError


def test_exception_summary_omits_message():
    try:
        raise ValueError(f"no se pudo leer {SECRET_NAME} {SECRET_ID}")
    except ValueError as exc:
        summary = exception_summary(exc)
    assert "ValueError" in summary and "test_privacy.py" in summary
    assert not any(s in summary for s in SECRETS)


def test_logs_never_contain_document_data(caplog, monkeypatch):
    """Procesa un lote en DEBUG forzando errores internos con datos en el mensaje."""
    caplog.set_level(logging.DEBUG)
    api = Api()

    real_anonymize = Api._anonymize
    calls = {"n": 0}

    def flaky(doc, options, item):
        calls["n"] += 1
        if calls["n"] == 2:  # el segundo documento falla con un mensaje que contiene datos
            raise RuntimeError(f"fallo con {SECRET_NAME} {SECRET_ID}")
        return real_anonymize(doc, options, item)

    monkeypatch.setattr(Api, "_anonymize", staticmethod(flaky))
    data = {"name": SECRET_FILE, "data": base64.b64encode(DOC.encode()).decode()}
    job = api.start_batch([data, data, {"name": SECRET_FILE, "data": "@@no-es-base64@@"}], {})
    assert job["items"][2]["status"] == "error"  # rechazado al encolar (base64 inválido)
    state = wait(api, job["job_id"])
    # En paralelo el orden de finalización varía: uno termina bien y el otro falla.
    assert sorted(i["status"] for i in state["items"]) == ["done", "error"]
    api.reprocess({"anonymize_professionals": True})

    logged = all_log_text(caplog)
    assert "RuntimeError" in logged  # el error se registra...
    assert not any(s in logged for s in SECRETS)  # ...pero sin datos
    assert "Epicrisis" not in logged  # ni el nombre del archivo


def test_page_errors_are_logged_without_content(caplog, monkeypatch, tmp_path):
    pytest.importorskip("reportlab")
    import make_samples

    pdf = tmp_path / "doc.pdf"
    make_samples.epicrisis_es(pdf)

    def boom(_page):
        raise ValueError("MARÍA FERNANDA ROJAS SILVA 15.234.567-K")

    monkeypatch.setattr(extract, "_extract_page_blocks", boom)
    caplog.set_level(logging.DEBUG)
    doc = load_bytes(pdf.name, pdf.read_bytes(), ocr_mode="off")
    assert any(w.startswith("page_error") for w in doc.warnings)
    logged = all_log_text(caplog)
    assert "ValueError" in logged and "ROJAS" not in logged and "15.234.567" not in logged


def test_third_party_loggers_stay_quiet_in_dev(monkeypatch):
    configure_logging(dev=True)
    try:
        assert logging.getLogger().level == logging.DEBUG
        for name in ("pdfminer", "pdfplumber", "PIL"):
            assert name in QUIET_LOGGERS
            assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
    finally:
        configure_logging(dev=False)


def test_logging_without_console_does_not_crash(monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)  # ejecutable --windowed
    configure_logging(dev=False)
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1 and isinstance(handlers[0], logging.NullHandler)
    log_exception(logging.getLogger("x"), "Error %s", RuntimeError("dato"), 1)  # no lanza
    monkeypatch.undo()
    configure_logging(dev=False)


# --------------------------------------------------------------------------- OCR sin temporales

def test_tesseract_receives_image_through_stdin(monkeypatch):
    """El OCR con Tesseract no crea archivos: imagen por stdin, texto por stdout."""
    calls = []

    def fake_run(cmd, input=None, **kwargs):
        calls.append((cmd, input, kwargs))
        out = b"List of available languages (2):\nspa\neng\n" if "--list-langs" in cmd else b"linea 1\nlinea 2\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr=b"")

    def no_temp(*_a, **_k):
        raise AssertionError("el OCR no debe crear archivos temporales")

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr, "_cache", {})
    monkeypatch.setattr(subprocess, "run", fake_run)
    for name in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile", "TemporaryDirectory"):
        monkeypatch.setattr(tempfile, name, no_temp)

    class FakeImage:
        def convert(self, _mode):
            return self

        def save(self, buffer, format):
            buffer.write(b"\x89PNG fake")

    class FakePage:
        def to_image(self, resolution):
            return type("I", (), {"original": FakeImage()})()

    assert ocr._ocr_tesseract(FakePage()) == ["linea 1", "linea 2"]
    cmd, data, kwargs = calls[-1]
    assert cmd[1:3] == ["stdin", "stdout"] and data.startswith(b"\x89PNG")
    assert "-l" in cmd and cmd[cmd.index("-l") + 1] == "spa+eng"
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_tesseract_errors_do_not_leak_stderr(monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr, "_cache", {"tess_langs": "spa"})
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, stdout=b"", stderr=f"Error near {SECRET_NAME}".encode()))

    class Page:
        def to_image(self, resolution):
            img = type("Img", (), {"convert": lambda self, m: self,
                                   "save": lambda self, b, format: b.write(b"png")})()
            return type("I", (), {"original": img})()

    with pytest.raises(RuntimeError) as err:
        ocr._ocr_tesseract(Page())
    assert SECRET_NAME not in str(err.value)


@pytest.mark.skipif(ocr.TESSERACT not in ocr.available_engines(), reason="Tesseract no instalado")
def test_real_ocr_leaves_no_temp_files(tmp_path, monkeypatch):
    pytest.importorskip("reportlab")
    import make_samples

    pdf = tmp_path / "doc.pdf"
    make_samples.lab_report_en(pdf)
    import pdfplumber

    with pdfplumber.open(pdf) as document:
        image = document.pages[0].to_image(resolution=120).original.convert("RGB")
    scan = tmp_path / "scan.pdf"
    image.save(scan)

    tmp_root = tmp_path / "tmp"
    tmp_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_root))
    monkeypatch.setenv("TEMP", str(tmp_root))
    monkeypatch.setenv("TMP", str(tmp_root))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_root))
    doc = load_bytes(scan.name, scan.read_bytes(), ocr_engine=ocr.TESSERACT)
    assert any(p.ocr for p in doc.pages)
    assert list(Path(tmp_root).iterdir()) == []


# --------------------------------------------------------------------------- DevTools

def test_devtools_only_from_source():
    assert main.dev_mode_allowed(True, frozen=False) is True
    assert main.dev_mode_allowed(True, frozen=True) is False
    assert main.dev_mode_allowed(False, frozen=False) is False


def test_dev_flag_ignored_in_frozen_build(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert main.parse_args(["--dev"]).dev is False
    monkeypatch.delattr(sys, "frozen")
    assert main.parse_args(["--dev"]).dev is True
