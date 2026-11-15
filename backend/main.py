"""Anonimize Medical — punto de entrada de la aplicación de escritorio.

Uso:
    python backend/main.py          # usa la interfaz compilada en frontend/dist
    python backend/main.py --dev    # usa el servidor de Vite (npm run dev) y abre DevTools
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import webview

from api import Api

APP_TITLE = "Anonimize Medical"
DEV_URL = "http://localhost:5173"


def resource_path(*parts: str) -> Path:
    """Ruta a recursos tanto en desarrollo como dentro del ejecutable de PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def find_frontend() -> Path:
    candidates = [resource_path("web", "index.html"), resource_path("frontend", "dist", "index.html")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "No se encontró la interfaz compilada. Ejecuta primero:\n"
        "    cd frontend && npm install && npm run build"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--dev", action="store_true", help="usar el servidor de desarrollo de Vite")
    parser.add_argument("--url", default=DEV_URL, help="URL del servidor de desarrollo")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.dev else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    url = args.url if args.dev else str(find_frontend())

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
    # private_mode=False permite que la interfaz recuerde preferencias (idioma, opciones).
    webview.start(debug=args.dev, http_server=not args.dev, private_mode=False)


if __name__ == "__main__":
    main()
