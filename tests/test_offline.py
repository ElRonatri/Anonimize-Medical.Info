"""Regla del proyecto: nada se descarga después del build; los motores pesados son opcionales."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

import main
from anonymizer import ocr

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

GUARD_SCRIPT = r"""
import socket, sys, threading, urllib.request
sys.path.insert(0, sys.argv[1])
from anonymizer.privacy import NetworkBlockedError, block_network
block_network()
block_network()  # idempotente

results = {}
for name, call in {
    "dns": lambda: socket.getaddrinfo("example.com", 443),
    "connect_ip": lambda: socket.create_connection(("93.184.215.14", 80), timeout=2),
    "urllib": lambda: urllib.request.urlopen("https://example.com", timeout=2),
    "urllib_via_local_proxy": lambda: urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": "http://127.0.0.1:3128"})).open("https://example.com", timeout=2),
}.items():
    try:
        call()
        results[name] = "ALLOWED"
    except NetworkBlockedError:
        results[name] = "blocked"
    except Exception as exc:  # urllib envuelve el error
        results[name] = "blocked" if "network_blocked" in repr(exc) else f"other:{exc!r}"

server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(1)
port = server.getsockname()[1]
threading.Thread(target=lambda: server.accept(), daemon=True).start()
socket.create_connection(("127.0.0.1", port), timeout=2).close()
results["loopback"] = "ok"
print(results)
"""


def test_network_guard_blocks_internet_but_not_loopback():
    # Con un proxy local configurado (como en muchos equipos corporativos) también se bloquea.
    env = {**os.environ, "HTTPS_PROXY": "http://127.0.0.1:3128", "HTTP_PROXY": "http://127.0.0.1:3128"}
    out = subprocess.run([sys.executable, "-c", GUARD_SCRIPT, str(BACKEND)], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    results = eval(out.stdout.strip())  # noqa: S307 - salida de nuestro propio script
    assert results == {"dns": "blocked", "connect_ip": "blocked", "urllib": "blocked",
                       "urllib_via_local_proxy": "blocked", "loopback": "ok"}


def test_rapidocr_without_bundled_models_is_disabled_not_downloaded(tmp_path, monkeypatch):
    package = tmp_path / "rapidocr"
    (package / "models").mkdir(parents=True)
    (package / "models" / "PP-OCRv6_det_small.onnx").write_bytes(b"x")  # faltan rec y cls
    fake = types.ModuleType("rapidocr")
    fake.__file__ = str(package / "__init__.py")

    def no_download(*_a, **_k):
        raise AssertionError("no debe instanciarse RapidOCR (descargaría los modelos que faltan)")

    fake.RapidOCR = no_download
    monkeypatch.setitem(sys.modules, "rapidocr", fake)
    monkeypatch.setattr(ocr, "_cache", {})
    monkeypatch.setattr(ocr, "_rapid_engine", None)
    assert ocr.rapid_model_paths() is None
    assert ocr.RAPIDOCR not in ocr.available_engines()
    with pytest.raises(RuntimeError, match="rapidocr_models_missing"):
        ocr._get_rapid()


def test_rapidocr_receives_explicit_model_paths(tmp_path, monkeypatch):
    package = tmp_path / "rapidocr"
    (package / "models").mkdir(parents=True)
    for name in ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx"):
        (package / "models" / name).write_bytes(b"x")
    received = {}
    fake = types.ModuleType("rapidocr")
    fake.__file__ = str(package / "__init__.py")
    fake.RapidOCR = lambda params: received.update(params) or object()
    monkeypatch.setitem(sys.modules, "rapidocr", fake)
    monkeypatch.setattr(ocr, "_cache", {})
    monkeypatch.setattr(ocr, "_rapid_engine", None)
    ocr._get_rapid()
    for key in ("Det.model_path", "Rec.model_path", "Cls.model_path"):
        assert Path(received[key]).is_file() and Path(received[key]).parent == package / "models"


def test_backend_has_no_download_code():
    """Ningún módulo propio usa clientes HTTP (sólo la interfaz local de PyWebView)."""
    pattern = re.compile(r"^\s*(?:import|from)\s+(requests|httpx|urllib\.request|http\.client|aiohttp)\b", re.M)
    offenders = [p.name for p in BACKEND.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_heavy_engines_are_opt_in_build_variants():
    spec = (ROOT / "anonimize.spec").read_text(encoding="utf-8")
    assert 'os.environ.get("BUNDLE_RAPIDOCR") == "1"' in spec
    assert 'excludes += ["rapidocr", "onnxruntime"]' in spec
    assert "BUNDLE_TESSERACT_DIR" in spec
    build = (ROOT / "build.bat").read_text(encoding="utf-8")
    assert 'if "%WITH_OCR%"=="1" set BUNDLE_RAPIDOCR=1' in build
    base_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "rapidocr" not in base_requirements and "onnxruntime" not in base_requirements
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "variant: [base, ocr, tesseract]" in ci


def test_self_test_fails_when_expected_ocr_engine_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "find_frontend", lambda: tmp_path / "index.html")
    monkeypatch.setattr(ocr, "available_engines", lambda: [])
    report = tmp_path / "r.json"
    assert main.main(["--self-test", "--expect-ocr", "rapidocr", "--self-test-report", str(report)]) == 1
    assert '"ocr_rapidocr": false' in report.read_text(encoding="utf-8")
