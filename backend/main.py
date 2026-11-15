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
from dataclasses import dataclass
from pathlib import Path

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
    args = parser.parse_args(argv)
    return Config(dev=dev_mode_allowed(args.dev, is_frozen()), url=args.url, self_test=args.self_test,
                  self_test_report=args.self_test_report)


# --------------------------------------------------------------------------- autoprueba

SELF_TEST_TEXT = (
    "Nombre: Juana Prueba Ficticia\nRUT: 11.111.111-1\nFecha de nacimiento: 01/01/1970\n"
    "La Sra. Ficticia refiere cefalea. Hemoglobina 13.1 g/dL.\n"
)


def self_test() -> dict:
    """Verifica que el motor, los exportadores y la interfaz empaquetada funcionen.

    Usa sólo datos ficticios y no escribe nada salvo el informe opcional.
    """
    from anonymizer import __version__, anonymize_document, load_text, ocr
    from anonymizer.exporters import export_bytes

    checks: dict[str, bool] = {}
    result = anonymize_document(load_text(SELF_TEST_TEXT), {"region": "CL"})
    text = result["text"]
    checks["anonymize"] = "Juana" not in text and "Ficticia" not in text and "[PACIENTE_1]" in text
    checks["clinical_values_kept"] = "13.1 g/dL" in text
    checks["export_docx"] = export_bytes("docx", text, result)[:2] == b"PK"
    checks["export_json"] = json.loads(export_bytes("json", text, result))["replacements"] > 0
    checks["frontend_bundled"] = find_frontend() is not None
    return {
        "ok": all(checks.values()),
        "version": __version__,
        "frozen": is_frozen(),
        "checks": checks,
        "ocr_engines": ocr.available_engines(),
    }


# --------------------------------------------------------------------------- aplicación

def run_window(config: Config) -> None:
    import webview

    from api import Api

    dev = config.dev
    url = config.url if dev else str(find_frontend() or "")
    if not dev and not url:
        raise SystemExit("No se encontró la interfaz compilada. Ejecuta: cd frontend && npm install && npm run build")

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

    # En Windows pywebview usa Edge WebView2 (incluido en Windows 10/11).
    # debug=True (DevTools, menú "Inspeccionar") sólo en desarrollo; ver dev_mode_allowed().
    # private_mode=False permite que la interfaz recuerde preferencias (idioma, tema, opciones);
    # nunca se guarda contenido clínico ni los términos personalizados (ver frontend/src/App.jsx).
    webview.start(debug=dev, http_server=not dev, private_mode=False)


def main(argv: list[str] | None = None) -> int:
    from anonymizer.privacy import configure_logging

    config = parse_args(argv)
    configure_logging(dev=config.dev)
    if "--dev" in (argv if argv is not None else sys.argv[1:]) and not config.dev:
        logging.getLogger(__name__).warning("--dev se ignora en el ejecutable distribuido")

    if config.self_test:
        try:
            report = self_test()
        except Exception as exc:  # el informe debe escribirse incluso si algo falla
            report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if config.self_test_report:
            config.self_test_report.write_text(payload, encoding="utf-8")
        else:
            print(payload)
        return 0 if report.get("ok") else 1

    run_window(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
