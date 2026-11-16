"""Garantías de privacidad operativa: logging sin contenido clínico.

Reglas:
* Los mensajes de log nunca incluyen texto de documentos, nombres de archivo (suelen contener
  el nombre del paciente), valores detectados ni opciones con términos del usuario.
* De las excepciones sólo se registra el TIPO y la pila de llamadas (archivo, línea, función).
  El mensaje de la excepción se omite: algunas lo construyen con fragmentos del contenido
  (p. ej. `UnicodeDecodeError` incluye los bytes que fallaron).
* Las librerías que leen el PDF (pdfminer, pdfplumber, PIL...) quedan en WARNING incluso en
  modo desarrollo: en DEBUG pdfminer puede volcar el contenido de las páginas.
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

# Librerías de terceros que procesan contenido del documento.
QUIET_LOGGERS = ("pdfminer", "pdfplumber", "PIL", "pypdfium2", "docx", "rapidocr", "RapidOCR",
                 "onnxruntime", "pytesseract", "bottle", "urllib3")


def exception_summary(exc: BaseException) -> str:
    """Tipo de la excepción y pila de llamadas, SIN el mensaje (que puede contener datos)."""
    frames = traceback.extract_tb(exc.__traceback__)
    stack = " <- ".join(f"{f.filename.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{f.lineno}:{f.name}"
                        for f in reversed(frames[-6:]))
    return f"{type(exc).__module__}.{type(exc).__qualname__} at {stack or '?'}"


def log_exception(logger: logging.Logger, message: str, exc: BaseException, *args: object) -> None:
    """Registra un error sin contenido clínico. `message` y `args` no deben llevar datos del documento."""
    logger.error(message + " [%s]", *args, exception_summary(exc))


def configure_logging(dev: bool = False) -> None:
    level = logging.DEBUG if dev else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    if sys.stderr is None:  # ejecutable sin consola (PyInstaller --windowed)
        root.addHandler(logging.NullHandler())
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- red

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", "", None}
_network_blocked = False


class NetworkBlockedError(PermissionError):
    """Intento de conexión a internet desde la aplicación (prohibido por diseño)."""


def _is_loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host in _LOOPBACK_HOSTS:
        return True
    return isinstance(host, str) and (host.startswith("127.") or host.lower() == "localhost")


_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY")


def _url_host(url: object) -> str:
    from urllib.parse import urlsplit

    return urlsplit(str(url)).hostname or ""


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event == "urllib.Request":  # cubre peticiones que irían por un proxy (local o del sistema)
        host = _url_host(args[0])
    elif event == "socket.getaddrinfo":
        host = args[0]
    elif event == "socket.connect" or event == "socket.sendto":
        address = args[1]
        if not isinstance(address, tuple):  # sockets AF_UNIX / pipes locales
            return
        host = address[0]
    else:
        return
    if not _is_loopback(host):
        raise NetworkBlockedError("network_blocked")


def block_network() -> None:
    """Prohíbe cualquier conexión de red que no sea local (127.0.0.1 / ::1) en este proceso.

    Garantía de "sin descargas después del build": ninguna librería (p. ej. un motor OCR que
    intente bajar modelos) puede conectarse a internet. Se implementa con un *audit hook*
    (PEP 578), que no se puede desinstalar. La interfaz (WebView2) corre en su propio proceso
    y sólo carga los archivos locales servidos desde 127.0.0.1.
    """
    global _network_blocked
    if not _network_blocked:
        # Un proxy en 127.0.0.1 (corporativo, depuradores) reenviaría el tráfico hacia afuera:
        # se anulan los proxies para que toda conexión sea directa y quede bloqueada. NO_PROXY=*
        # también desactiva el proxy configurado en el registro de Windows (urllib/requests).
        import os

        for name in _PROXY_VARS:
            os.environ.pop(name, None)
            os.environ.pop(name.lower(), None)
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
        sys.addaudithook(_audit)
        _network_blocked = True


def network_blocked() -> bool:
    return _network_blocked
