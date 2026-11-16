"""Anonimize Medical — punto de entrada de la aplicación de escritorio.

Uso:
    python backend/main.py               # usa la interfaz compilada en frontend/dist
    python backend/main.py --dev         # servidor de Vite (npm run dev) + DevTools (sólo desde el código)
    AnonimizeMedical.exe --self-test --self-test-report informe.json
                                         # verificación sin ventana (usada por el CI de Windows)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_TITLE = "Anonimize Medical"
DEV_URL = "http://localhost:5173"


def is_frozen() -> bool:
    """True dentro del ejecutable generado por PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """Ruta a recursos tanto en desarrollo como dentro del ejecutable de PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def find_frontend() -> Path | None:
    candidates = [resource_path("web", "index.html"), resource_path("frontend", "dist", "index.html")]
    return next((c for c in candidates if c.is_file()), None)


# --------------------------------------------------------------------------- argumentos

@dataclass(frozen=True)
class Config:
    dev: bool
    url: str
    self_test: bool
    self_test_report: Path | None
    expect_ocr: str | None = None
    expect_ner: bool = False
    privacy_probe: Path | None = None
    probe_sentinel: str = ""
    probe_crash: bool = False
    probe_hold: float = 5.0


def dev_mode_allowed(requested: bool, frozen: bool) -> bool:
    """DevTools sólo desde el código fuente (run-dev.bat), nunca en el ejecutable distribuido.

    En el .exe, `--dev` se ignora: abriría las herramientas de desarrollo (inspección del DOM,
    consola con acceso al texto del documento) y apuntaría a un servidor local de Vite.
    """
    return requested and not frozen


def parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--dev", action="store_true", help="servidor de desarrollo de Vite + DevTools")
    parser.add_argument("--url", default=DEV_URL, help="URL del servidor de desarrollo")
    parser.add_argument("--self-test", action="store_true", help="verificar la instalación sin abrir la ventana")
    parser.add_argument("--self-test-report", type=Path, help="archivo JSON donde escribir el resultado")
    parser.add_argument("--expect-ocr", choices=["tesseract", "rapidocr"],
                        help="(autoprueba) exigir que este motor OCR funcione sin conexión")
    parser.add_argument("--expect-ner", action="store_true",
                        help="(autoprueba) exigir que la pasada NER funcione sin conexión")
    probe = parser.add_argument_group("sonda de privacidad (CI)")
    probe.add_argument("--privacy-probe", type=Path, metavar="CARPETA",
                       help="usar la ventana real con un dato centinela y escribir un informe (ver privacy_probe.py)")
    probe.add_argument("--probe-sentinel", default="", help="nombre sintético único, p. ej. 'Zxqwerty Centinela Qwmzk'")
    probe.add_argument("--probe-crash", action="store_true", help="terminar de golpe al final (simula un fallo)")
    probe.add_argument("--probe-hold", type=float, default=5.0, help="segundos con la ventana abierta al final")
    args = parser.parse_args(argv)
    if args.privacy_probe and len(args.probe_sentinel.split()) < 3:
        parser.error("--privacy-probe requiere --probe-sentinel con nombre y dos apellidos")
    return Config(dev=dev_mode_allowed(args.dev, is_frozen()), url=args.url, self_test=args.self_test,
                  self_test_report=args.self_test_report, expect_ocr=args.expect_ocr,
                  expect_ner=args.expect_ner, privacy_probe=args.privacy_probe,
                  probe_sentinel=args.probe_sentinel, probe_crash=args.probe_crash, probe_hold=args.probe_hold)


# --------------------------------------------------------------------------- autoprueba

SELF_TEST_TEXT = (
    "Nombre: Juana Prueba Ficticia\nRUT: 11.111.111-1\nFecha de nacimiento: 01/01/1970\n"
    "La Sra. Ficticia refiere cefalea. Hemoglobina 13.1 g/dL.\n"
)


def _network_is_blocked() -> bool:
    """Intenta resolver un dominio externo: debe fallar con NetworkBlockedError."""
    import socket

    from anonymizer.privacy import NetworkBlockedError, network_blocked

    if not network_blocked():
        return False
    try:
        socket.getaddrinfo("example.com", 443)
    except NetworkBlockedError:
        return True
    except OSError:
        return False
    return False


def _parallel_batch_works() -> bool:
    """Un lote de 3 textos ficticios con 2 procesos de extracción (prueba spawn/freeze_support)."""
    import base64
    import os
    import time

    from api import Api

    api = Api()
    try:
        files = [{"name": f"ficticio_{n}.txt", "data": base64.b64encode(SELF_TEST_TEXT.encode()).decode()}
                 for n in range(3)]
        job = api.start_batch(files, {"max_workers": 2, "parallel": "force"})
        deadline = time.monotonic() + 120
        state = api.get_job(job["job_id"])
        while not state["done"] and time.monotonic() < deadline:
            time.sleep(0.1)
            state = api.get_job(job["job_id"])
        pids = {item["worker"] for item in state["items"]}
        return (state["done"] and all(item["status"] == "done" for item in state["items"])
                and os.getpid() not in pids)
    finally:
        api.shutdown()


def _ocr_works(engine: str) -> bool:
    """OCR real, sin conexión, sobre una página sintética generada en memoria."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    from anonymizer import load_bytes, ocr

    if engine not in ocr.available_engines():
        return False
    image = Image.new("RGB", (1240, 400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=56)
    draw.text((60, 80), "Nombre: Juana Prueba", fill="black", font=font)
    draw.text((60, 200), "Hemoglobina 13.1 g/dL", fill="black", font=font)
    pdf = io.BytesIO()
    image.save(pdf, format="PDF", resolution=150)
    doc = load_bytes("selftest.pdf", pdf.getvalue(), ocr_mode="force", ocr_engine=engine)
    text = doc.full_text().lower()
    return any(p.ocr for p in doc.pages) and "prueba" in text and "hemoglobina" in text


def _ner_works() -> bool:
    """La pasada NER oculta un nombre SIN etiqueta (que las reglas no detectan), sin red."""
    from anonymizer import anonymize_document, load_text, ner

    if not ner.available("es"):
        return False
    text = "Paciente estable.\nAyer se conversó con su hija Bernardita Quiroga sobre el control."
    out = anonymize_document(load_text(text), {"ner": True, "output_format": "text"})["text"]
    return "Bernardita" not in out and "Quiroga" not in out and "control" in out


def self_test(expect_ocr: str | None = None, expect_ner: bool = False) -> dict[str, Any]:
    """Verifica que el motor, los exportadores y la interfaz empaquetada funcionen.

    Usa sólo datos ficticios y no escribe nada salvo el informe opcional.
    """
    from anonymizer import __version__, anonymize_document, detector, fastmatch, identifiers, load_text, ocr
    from anonymizer.exporters import export_bytes
    from anonymizer.ner import info as ner_info

    checks: dict[str, bool] = {}
    result = anonymize_document(load_text(SELF_TEST_TEXT), {"region": "CL"})
    text = result["text"]
    checks["anonymize"] = "Juana" not in text and "Ficticia" not in text and "[PACIENTE_1]" in text
    checks["clinical_values_kept"] = "13.1 g/dL" in text
    checks["export_docx"] = export_bytes("docx", text, result)[:2] == b"PK"
    checks["export_json"] = json.loads(export_bytes("json", text, result))["replacements"] > 0
    checks["frontend_bundled"] = find_frontend() is not None
    checks["aho_corasick"] = fastmatch.AVAILABLE  # pyahocorasick empaquetado
    # Reglas por país (data/identifiers/*.json) empaquetadas y con su validador.
    checks["country_rules"] = (len(identifiers.ESTRUCTURALES) >= 34
                               and identifiers.anonimizar("RUN 12.345.678-5") == "RUN [RUN_CL]")
    checks["network_blocked"] = _network_is_blocked()
    checks["parallel_batch"] = _parallel_batch_works()
    if expect_ocr:
        checks[f"ocr_{expect_ocr}"] = _ocr_works(expect_ocr)
    if expect_ner:
        checks["ner"] = _ner_works()
    return {
        "ok": all(checks.values()),
        "version": __version__,
        "frozen": is_frozen(),
        "checks": checks,
        "ocr_engines": ocr.available_engines(),
        "literal_engine": detector.literal_engine(),
        "ner": ner_info(),
        "tesseract_cmd": ocr.find_tesseract(),  # ruta del ejecutable usado (para verificar el empaquetado)
    }


# --------------------------------------------------------------------------- aplicación

def run_window(config: Config, on_loaded: Callable[[Any, Any], None] | None = None) -> None:
    """Abre la ventana. `on_loaded(window, api)` corre en un hilo al cargar la página (sonda de privacidad)."""
    import webview

    import appdata
    from api import Api

    dev = config.dev
    url = config.url if dev else str(find_frontend() or "")
    if not dev and not url:
        raise SystemExit("No se encontró la interfaz compilada. Ejecuta: cd frontend && npm install && npm run build")

    # Perfil de WebView2 en una carpeta propia, en modo privado: nada de la página (caché,
    # Local Storage, IndexedDB, volcados de Crashpad) sobrevive al cierre. Se limpia también al
    # iniciar, por si un cierre por error dejó restos. Las preferencias van a prefs.json (backend).
    profile = appdata.webview_profile_dir()
    appdata.cleanup_webview_profile(profile)
    appdata.configure_webview2_environment()

    api = Api()
    window = webview.create_window(
        APP_TITLE,
        url=url,
        js_api=api,
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color="#0f172a",
        text_select=True,
    )
    api._set_window(window)
    if on_loaded is not None:
        window.events.loaded += lambda *_: threading.Thread(
            target=on_loaded, args=(window, api), name="on-loaded", daemon=True).start()

    # En Windows pywebview usa Edge WebView2 (incluido en Windows 10/11).
    # debug=True (DevTools, menú "Inspeccionar") sólo en desarrollo; ver dev_mode_allowed().
    try:
        webview.start(debug=dev, http_server=not dev, private_mode=True, storage_path=str(profile))
    finally:
        api.shutdown()  # cierra los procesos de extracción
        appdata.cleanup_webview_profile(profile)


def main(argv: list[str] | None = None) -> int:
    from anonymizer.privacy import block_network, configure_logging, limit_crash_dumps

    config = parse_args(argv)
    configure_logging(dev=config.dev)
    # Sin descargas ni conexiones externas: sólo se permite la red local (interfaz en 127.0.0.1).
    block_network()
    limit_crash_dumps()  # informes de error de Windows sin el heap (texto de los documentos)
    if "--dev" in (argv if argv is not None else sys.argv[1:]) and not config.dev:
        logging.getLogger(__name__).warning("--dev se ignora en el ejecutable distribuido")

    if config.self_test:
        try:
            report = self_test(config.expect_ocr, config.expect_ner)
        except Exception as exc:  # el informe debe escribirse incluso si algo falla
            report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if config.self_test_report:
            config.self_test_report.write_text(payload, encoding="utf-8")
        else:
            print(payload)
        return 0 if report.get("ok") else 1

    if config.privacy_probe:
        import privacy_probe

        return privacy_probe.run(config, config.privacy_probe, config.probe_sentinel,
                                 crash=config.probe_crash, hold=config.probe_hold)

    run_window(config)
    return 0


if __name__ == "__main__":
    # Imprescindible en el ejecutable de PyInstaller: los procesos de extracción en paralelo
    # relanzan el .exe y deben ejecutar su tarea en lugar de abrir otra ventana.
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
