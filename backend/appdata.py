"""Qué deja la aplicación en el disco del usuario, y nada más.

* **Preferencias** (``prefs.json``): idioma, tema, opciones y el aviso de uso responsable, validadas
  contra una lista cerrada de claves y tipos. Lo que no está en la lista se descarta, de modo que
  ningún texto clínico puede terminar ahí aunque la interfaz lo enviara por error. Los términos a
  ocultar (``custom_terms``, suelen ser nombres de pacientes) nunca se guardan.
* **Perfil de WebView2** (caché, Local Storage, IndexedDB, Crashpad...): la ventana se abre en modo
  privado con un perfil en una carpeta propia que se borra al cerrar y, si quedó de un cierre por
  error, al volver a abrir la aplicación (:func:`cleanup_webview_profile`).

Rutas en Windows: ``%APPDATA%\\AnonimizeMedical\\prefs.json`` y
``%LOCALAPPDATA%\\AnonimizeMedical\\WebView2`` (sesión). La variable ``ANONIMIZE_DATA_DIR``
reemplaza ambas raíces (pruebas y CI). Ver ``docs/privacidad-en-disco.md``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

APP_DIR_NAME = "AnonimizeMedical"
ENV_DATA_DIR = "ANONIMIZE_DATA_DIR"
PREFS_FILE = "prefs.json"
PROFILE_DIR = "WebView2"

# Argumentos para el navegador de WebView2: sin informes de fallos (los volcados de memoria
# podrían contener la página, es decir, texto clínico). pywebview fija su propio argumento;
# se repite aquí porque la variable de entorno de WebView2 lo reemplaza.
WEBVIEW2_ARGS_ENV = "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"
WEBVIEW2_ARGS = (
    "--disable-features=ElasticOverscroll",
    "--disable-breakpad",
    "--disable-crash-reporter",
)

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- rutas

def _roots() -> tuple[Path, Path]:
    """(raíz de preferencias, raíz de datos locales)."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        base = Path(override)
        return base, base
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(roaming) / APP_DIR_NAME, Path(local) / APP_DIR_NAME
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "anonimize-medical"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "anonimize-medical"
    return config, cache


def prefs_path() -> Path:
    return _roots()[0] / PREFS_FILE


def webview_profile_dir() -> Path:
    return _roots()[1] / PROFILE_DIR


# --------------------------------------------------------------------------- perfil de WebView2

def cleanup_webview_profile(path: Path | None = None, attempts: int = 10, delay: float = 0.3) -> bool:
    """Borra el perfil de sesión de WebView2. Reintenta: el navegador tarda en soltar los archivos.

    Devuelve True si la carpeta ya no existe.
    """
    path = path or webview_profile_dir()
    for attempt in range(attempts):
        if not path.exists():
            return True
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        if attempt < attempts - 1:
            time.sleep(delay)
    log.warning("No se pudo borrar por completo el perfil temporal de la ventana")
    return False


def configure_webview2_environment(env: dict[str, str] | None = None) -> None:
    """Fija los argumentos del navegador de WebView2 (sin informes de fallos)."""
    target = os.environ if env is None else env
    target[WEBVIEW2_ARGS_ENV] = " ".join(WEBVIEW2_ARGS)


# --------------------------------------------------------------------------- preferencias

_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
MAX_WHITELIST_ITEMS = 1000
MAX_WHITELIST_CHARS = 200


def _token(value: Any) -> bool:
    return isinstance(value, str) and bool(_TOKEN.match(value))


def _bool(value: Any) -> bool:
    return isinstance(value, bool)


def _workers(value: Any) -> bool:
    return value == "auto" or (isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 64)


def _threshold(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _whitelist(value: Any) -> bool:
    # Términos que el usuario decidió NO ocultar (p. ej. «Hospital Regional»): no son datos del paciente.
    return (isinstance(value, list) and len(value) <= MAX_WHITELIST_ITEMS
            and all(isinstance(v, str) and 0 < len(v) <= MAX_WHITELIST_CHARS and "\n" not in v for v in value))


OPTION_RULES: dict[str, Any] = {
    "language": _token, "output_format": _token, "replacement_style": _token, "region": _token,
    "ocr_mode": _token, "ocr_engine": _token,
    "anonymize_professionals": _bool, "anonymize_all_dates": _bool, "anonymize_addresses": _bool,
    "remove_repeated": _bool, "page_markers": _bool, "aggressive_numbers": _bool,
    "ner": _bool, "ner_orgs": _bool,
    "max_workers": _workers, "ner_threshold": _threshold, "whitelist": _whitelist,
}


def _options(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    return {k: v for k, v in value.items() if k in OPTION_RULES and OPTION_RULES[k](v)}


PREF_RULES: dict[str, Any] = {
    "uiLanguage": lambda v: v if v in ("es", "en") else None,
    "theme": lambda v: v if v in ("light", "dark") else None,
    "exportGeneric": lambda v: v if isinstance(v, bool) else None,
    "responsibleUseDismissed": lambda v: v if isinstance(v, bool) else None,
    "options": _options,
}


def sanitize_pref(key: str, value: Any) -> Any:
    """Valor aceptado para la preferencia, o None si la clave o el valor no están permitidos."""
    rule = PREF_RULES.get(key)
    return None if rule is None else rule(value)


class PrefStore:
    """Preferencias en un JSON pequeño, escrito de forma atómica y validado al leer y al escribir."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or prefs_path()
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        clean = {k: sanitize_pref(k, v) for k, v in raw.items()}
        return {k: v for k, v in clean.items() if v is not None}

    def set(self, key: str, value: Any) -> bool:
        clean = sanitize_pref(key, value)
        if clean is None:
            return False
        with self._lock:
            data = self.load()
            data[key] = clean
            self._write(data)
        return True

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # atómico: nunca queda un archivo a medias
