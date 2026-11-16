"""Validadores de dígito verificador y su registro.

Las reglas por país (``data/identifiers/countries/*.json``) nombran su validador con una clave
(p. ej. ``"run_cl"``). Para añadir uno nuevo **no hace falta tocar** ``identifiers.py``:

* en este módulo, decorando la función con ``@register("clave")``; o
* desde un paquete instalado aparte (plugin), declarando un *entry point* en el grupo
  ``anonimize_medical.validators`` que apunte a una función ``(str) -> bool``.
  Se cargan con :func:`load_plugins` (sólo al ejecutar desde el código fuente: el ejecutable
  congelado no instala paquetes ni descarga nada).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from importlib import metadata

Validator = Callable[[str], bool]

ENTRY_POINT_GROUP = "anonimize_medical.validators"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REGISTRY: dict[str, Validator] = {}
log = logging.getLogger(__name__)


def register(name: str, *, replace: bool = False) -> Callable[[Validator], Validator]:
    """Decorador que registra un validador con la clave ``name``: ``@register("run_cl")``."""
    if not _KEY_RE.match(name):
        raise ValueError(f"clave de validador inválida: {name!r} (minúsculas, dígitos y _)")

    def deco(func: Validator) -> Validator:
        if name in _REGISTRY and _REGISTRY[name] is not func and not replace:
            raise ValueError(f"validador ya registrado: {name!r}")
        _REGISTRY[name] = func
        return func

    return deco


def get(name: str) -> Validator:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"validador desconocido: {name!r}; disponibles: {', '.join(sorted(_REGISTRY))}") from None


def names() -> list[str]:
    return sorted(_REGISTRY)


def load_plugins() -> list[str]:
    """Registra los validadores declarados por paquetes instalados (entry points). Devuelve las claves."""
    loaded = []
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            func = ep.load()
            if not callable(func):
                raise TypeError("no es invocable")
            register(ep.name, replace=True)(func)
            loaded.append(ep.name)
        except Exception as exc:  # un plugin defectuoso no debe impedir iniciar la aplicación
            log.warning("No se pudo cargar el validador %s: %s", ep.name, type(exc).__name__)
    return loaded


_NO_DIGITOS = re.compile(r"\D")


def _digits(s: str) -> str:
    return _NO_DIGITOS.sub("", s)


# ----------------------------------------------------------------------------
# Validadores de dígito verificador
# ----------------------------------------------------------------------------
def v_run_cl(s: str) -> bool:
    s = s.replace(".", "").replace("-", "").upper()
    cuerpo, dv = s[:-1], s[-1]
    suma, m = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * m
        m = m + 1 if m < 7 else 2
    r = 11 - suma % 11
    esperado = "0" if r == 11 else "K" if r == 10 else str(r)
    return dv == esperado


def v_cuit_ar(s: str) -> bool:
    d = _digits(s)
    if len(d) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    r = 11 - sum(int(a) * b for a, b in zip(d, pesos, strict=False)) % 11
    r = 0 if r == 11 else r
    return r != 10 and r == int(d[10])


def v_cpf_br(s: str) -> bool:
    d = _digits(s)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        r = sum(int(d[i]) * (n + 1 - i) for i in range(n)) * 10 % 11
        if r % 10 != int(d[n]):
            return False
    return True


def v_cns_br(s: str) -> bool:
    d = _digits(s)
    return len(d) == 15 and d[0] in "12789" and \
        sum(int(x) * (15 - i) for i, x in enumerate(d)) % 11 == 0


def v_ci_ec(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10:
        return False
    prov, tercero = int(d[:2]), int(d[2])
    if not (1 <= prov <= 24 or prov == 30) or tercero >= 6:
        return False
    suma = 0
    for i in range(9):
        p = int(d[i]) * (2 if i % 2 == 0 else 1)
        suma += p - 9 if p > 9 else p
    return (10 - suma % 10) % 10 == int(d[9])


def v_ci_uy(s: str) -> bool:
    d = _digits(s)
    if not 7 <= len(d) <= 8:
        return False
    cuerpo, dv = d[:-1].zfill(7), int(d[-1])
    suma = sum(int(a) * b for a, b in zip(cuerpo, [2, 9, 8, 7, 6, 3, 4], strict=False))
    return (10 - suma % 10) % 10 == dv


_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def v_dni_es(s: str) -> bool:
    s = s.replace("-", "").replace(" ", "").upper()
    return _LETRAS_DNI[int(s[:8]) % 23] == s[8]


def v_nie_es(s: str) -> bool:
    s = s.replace("-", "").replace(" ", "").upper()
    num = str("XYZ".index(s[0])) + s[1:8]
    return _LETRAS_DNI[int(num) % 23] == s[8]


def v_nir_fr(s: str) -> bool:
    s = s.replace(" ", "").upper()
    if len(s) != 15:
        return False
    cuerpo = s[:13].replace("2A", "19").replace("2B", "18")
    if not cuerpo.isdigit():
        return False
    return 97 - int(cuerpo) % 97 == int(s[13:])


def v_id_cn(s: str) -> bool:
    s = s.upper()
    pesos = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    suma = sum(int(a) * b for a, b in zip(s[:17], pesos, strict=False))
    return "10X98765432"[suma % 11] == s[17]


_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
       [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
       [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
       [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def v_aadhaar_in(s: str) -> bool:
    d = _digits(s)
    c = 0
    for i, x in enumerate(reversed(d)):
        c = _VD[c][_VP[i % 8][int(x)]]
    return len(d) == 12 and c == 0


def v_nhs_uk(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10:
        return False
    r = 11 - sum(int(d[i]) * (10 - i) for i in range(9)) % 11
    r = 0 if r == 11 else r
    return r != 10 and r == int(d[9])


def v_luhn(s: str) -> bool:
    d = _digits(s)
    suma = 0
    for i, x in enumerate(reversed(d)):
        n = int(x)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        suma += n
    return suma % 10 == 0


def v_hetu_fi(s: str) -> bool:
    s = s.upper()
    n = int(s[:6] + s[7:10])
    return "0123456789ABCDEFHJKLMNPRSTUVWXY"[n % 31] == s[10]


def v_mrz_cd(campo: str, dv: str) -> bool:
    """Dígito verificador ICAO 9303 (pesos 7-3-1)."""
    def val(c):
        if c.isdigit():
            return int(c)
        if c == "<":
            return 0
        return ord(c) - 55
    pesos = [7, 3, 1]
    return sum(val(c) * pesos[i % 3] for i, c in enumerate(campo)) % 10 == int(dv)


def v_mrz_td3_l2(s: str) -> bool:
    # Valida N° de documento, fecha de nacimiento y vencimiento.
    return (v_mrz_cd(s[0:9], s[9]) and v_mrz_cd(s[13:19], s[19])
            and v_mrz_cd(s[21:27], s[27]))


# Registro de los validadores incluidos: v_run_cl -> "run_cl", etc.
for _name, _func in list(globals().items()):
    if _name.startswith("v_") and _name != "v_mrz_cd" and callable(_func):
        register(_name[2:])(_func)
