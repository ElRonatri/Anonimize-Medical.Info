"""
Identificadores personales por país (documentos nacionales, pasaporte, seguridad
social, salud, ficha clínica) para textos clínicos.

Tres capas:
  1. ESTRUCTURALES: formatos con estructura propia (letras, separadores o
     longitud) + validación de dígito verificador cuando existe. No requieren
     contexto. Ej.: RUN 12.345.678-5, CURP, CPF 123.456.789-09, NIR francés.
     Se filtran según el país / región elegidos en la interfaz.
  2. CONTEXTUALES: palabra clave + valor. Cubre los identificadores que son
     solo dígitos y que sin contexto se confunden con cualquier número
     (DNI peruano, CC colombiana, PESEL, BSN, pasaporte, ficha clínica, etc.).
  3. AGRESIVA (opcional): enmascara cualquier secuencia de >= 7 dígitos.

Las reglas (formatos, países, regiones y palabras clave) se cargan desde
data/identifiers/*.json y los validadores desde validators.py: ver
docs/reglas-por-pais.md.

Uso independiente:
    from anonymizer.identifiers import anonimizar
    anonimizar("Paciente RUN 12.345.678-5, pasaporte AB123456")
    -> "Paciente RUN [RUN_CL], pasaporte [PASAPORTE]"
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from . import country_rules, validators
from .validators import _digits

# Límites de token: no pegado a letras/dígitos.
B = r"(?<![A-Za-z0-9])"
E = r"(?![A-Za-z0-9])"


_NO_ALNUM_MAYUS = re.compile(r"[^A-Z0-9]+")

# Las reglas por país viven en data/identifiers/*.json (ver country_rules.py) y los validadores
# de dígito verificador en validators.py: añadir un país no requiere tocar este módulo.
validators.load_plugins()
RULES = country_rules.load()


# ----------------------------------------------------------------------------
# Capa 1: patrones estructurales
# ----------------------------------------------------------------------------
@dataclass
class Patron:
    etiqueta: str          # se usa como reemplazo: [ETIQUETA]
    pais: str
    nombre: str
    regex: str
    validador: Callable[[str], bool] | None = None
    flags: int = 0


ESTRUCTURALES: list[Patron] = [
    Patron(r.label, r.country, r.name, r.regex, validators.get(r.validator) if r.validator else None, r.flags)
    for r in RULES.patterns
]

# País del patrón -> códigos ISO 3166-1 alfa-2 ("*" = se aplica en cualquier región).
PAIS_CODIGOS: dict[str, tuple[str, ...]] = dict(RULES.country_codes)

# Regiones seleccionables en la interfaz. Los países sin patrón estructural propio
# (p. ej. Colombia, Perú, Alemania) usan la capa contextual (palabra clave + valor).
REGIONES: dict[str, tuple[str, ...]] = dict(RULES.regions)

GENERAL = "general"  # sin capa por país (comportamiento base de la aplicación)
ALL = "all"


def resolver_region(region: str | None) -> frozenset[str] | None:
    """Devuelve los códigos de país activos, frozenset() vacío = todos, None = desactivado."""
    if not region or region == GENERAL:
        return None
    region = region.strip()
    if region == ALL:
        return frozenset()
    if region in REGIONES:
        return frozenset(REGIONES[region])
    return frozenset({region.upper()})


def formatos_por_pais() -> dict[str, list[str]]:
    """Código de país -> nombres de los formatos estructurales validados (para la interfaz)."""
    out: dict[str, list[str]] = {}
    for p in ESTRUCTURALES:
        for code in PAIS_CODIGOS.get(p.pais, ()):
            if code != "*" and p.nombre not in out.setdefault(code, []):
                out[code].append(p.nombre)
    return out


def patrones_para(paises: frozenset[str] | None) -> list[tuple[Patron, re.Pattern]]:
    if paises is None:
        return []
    if not paises:  # todas
        return _COMPILADOS
    return [(p, rx) for p, rx in _COMPILADOS
            if "*" in PAIS_CODIGOS.get(p.pais, ()) or paises & set(PAIS_CODIGOS.get(p.pais, ()))]


# ----------------------------------------------------------------------------
# Capa 2: palabra clave + valor
# ----------------------------------------------------------------------------
# Insensibles a mayúsculas. Orden: más largas primero (lo hace el código).
KW_CI: list[str] = RULES.keywords_ci
# Sensibles a mayúsculas: siglas que también son palabras o sílabas comunes
# ("sin", "pan", "ce", "cc", "bi", "ins"...). Solo se detectan en MAYÚSCULAS.
KW_CS: list[str] = RULES.keywords_cs

_SEP = r"(?i:\s*(?:n[°ºo]\.?|nro\.?|n[uú]m(?:ero)?\.?|number|#|:|=|-)\s*)*\s*"
# Valor: alfanumérico; une partes con . - / y con espacio solo si sigue un dígito.
_VALOR = r"[A-Za-z0-9](?:[A-Za-z0-9]|[./-](?=[A-Za-z0-9])|[ \t](?=\d)){3,24}"

_kw_ci = "|".join(sorted(KW_CI, key=len, reverse=True))
_kw_cs = "|".join(sorted(KW_CS, key=len, reverse=True))
# Se aplica sobre el texto completo: los espacios nunca cruzan saltos de línea.
CONTEXTUAL = re.compile((
    B + r"(?P<kw>(?i:" + _kw_ci + r")|(?:" + _kw_cs + r"))\.?" + E + _SEP
    + r"(?P<valor>" + _VALOR + r")" + r"(?![A-Za-z0-9])"
).replace(r"\s", r"[ \t]"))


def _contextual(kw: str, primera: str) -> re.Pattern:
    # La anticipación del primer carácter permite descartar rápido las posiciones imposibles.
    return re.compile((
        f"(?={primera})" + B + r"(?P<kw>" + kw + r")\.?" + E + _SEP
        + r"(?P<valor>" + _VALOR + r")" + r"(?![A-Za-z0-9])"
    ).replace(r"\s", r"[ \t]"))


# Palabras clave insensibles a mayúsculas: se buscan en minúsculas sobre el texto en minúsculas
# (sin IGNORECASE, ≈2x más rápido). Las siglas sensibles, sobre el texto original.
CONTEXTUAL_CI = _contextual(_kw_ci, "[a-z]")
CONTEXTUAL_CS = _contextual(_kw_cs, "[A-Z]")
_MINUSCULAS = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
_MINUSCULAS.update({c: c + 32 for c in range(0xC0, 0xDF) if c != 0xD7})

_ETIQUETA_KW: list[tuple[str, str]] = RULES.label_rules


_ETIQUETA_KW_RE = [(re.compile(patron), etiqueta) for patron, etiqueta in _ETIQUETA_KW]


def _etiqueta_contextual(kw: str) -> str:
    k = kw.strip().lower()
    for patron, etiqueta in _ETIQUETA_KW_RE:
        if patron.search(k):
            return etiqueta
    return "ID_" + _NO_ALNUM_MAYUS.sub("_", kw.strip().upper()).strip("_")[:20]


# ----------------------------------------------------------------------------
# Capa 3: agresiva
# ----------------------------------------------------------------------------
# Secuencias de >= 7 dígitos (permitiendo . - espacio entre grupos). Excluye
# fechas (dd-mm-aaaa / aaaa-mm-dd) para no destruir la cronología clínica.
AGRESIVO = re.compile(B + r"\d(?:\d|[.\- ](?=\d)){6,}\d?" + E)
_FECHA = re.compile(r"^(?:\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})$")


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
@dataclass
class Hallazgo:
    inicio: int
    fin: int
    texto: str
    etiqueta: str
    capa: str  # "estructural" | "contextual" | "agresiva"


def _primer_caracter(cuerpo: str) -> str | None:
    """Clase del primer carácter de un patrón (para una anticipación rápida), o None."""
    while cuerpo.startswith("(?!"):  # saltar anticipaciones negativas iniciales
        nivel, i = 0, 0
        for i, c in enumerate(cuerpo):
            if c == "(" and (i == 0 or cuerpo[i - 1] != "\\"):
                nivel += 1
            elif c == ")" and cuerpo[i - 1] != "\\":
                nivel -= 1
                if nivel == 0:
                    break
        cuerpo = cuerpo[i + 1:]
    if cuerpo.startswith(r"\d"):
        return r"\d"
    if cuerpo.startswith("["):
        fin = cuerpo.find("]", 1)
        return cuerpo[:fin + 1] if fin > 0 else None
    if cuerpo[:1].isalnum():
        return re.escape(cuerpo[0])
    return None


def _compilar(p: Patron) -> re.Pattern:
    """Precompila el patrón anteponiendo una anticipación del primer carácter.

    Las expresiones empiezan con un lookbehind, lo que impide al motor descartar
    rápido las posiciones imposibles; la anticipación (?=[...]) lo vuelve ~3x más rápido.
    """
    regex = p.regex
    if regex.startswith(B) and "|" + B not in regex:
        primero = _primer_caracter(regex[len(B):])
        if primero:
            regex = f"(?={primero})" + regex
    return re.compile(regex, p.flags)


_COMPILADOS = [(p, _compilar(p)) for p in ESTRUCTURALES]


def estructurales(texto: str, paises: frozenset[str] | None = frozenset(),
                  validar: bool = True) -> list[Hallazgo]:
    hallazgos = []
    for p, rx in patrones_para(paises):
        for m in rx.finditer(texto):
            if validar and p.validador:
                try:
                    if not p.validador(m.group(0)):
                        continue
                except (ValueError, IndexError):
                    continue
            hallazgos.append(Hallazgo(m.start(), m.end(), m.group(0), p.etiqueta, "estructural"))
    return hallazgos


def contextuales(texto: str) -> list[Hallazgo]:
    hallazgos = []
    minusculas = texto.lower()
    if len(minusculas) != len(texto):  # algunos caracteres Unicode cambian de longitud
        minusculas = texto.translate(_MINUSCULAS)
    coincidencias = [(m, texto) for m in CONTEXTUAL_CI.finditer(minusculas)]
    coincidencias += [(m, texto) for m in CONTEXTUAL_CS.finditer(texto)]
    for m, _ in coincidencias:
        valor = texto[m.start("valor"):m.end("valor")].rstrip(".-/ ")
        if sum(c.isdigit() for c in valor) < 4 or _FECHA.match(valor):
            continue
        ini = m.start("valor")
        kw = texto[m.start("kw"):m.end("kw")]
        hallazgos.append(Hallazgo(ini, ini + len(valor), valor, _etiqueta_contextual(kw), "contextual"))
    return hallazgos


def agresivos(texto: str) -> list[Hallazgo]:
    return [Hallazgo(m.start(), m.end(), m.group(0), "NUMERO", "agresiva")
            for m in AGRESIVO.finditer(texto)
            if not _FECHA.match(m.group(0)) and len(_digits(m.group(0))) >= 7]


def encontrar(texto: str, agresivo: bool = False, validar: bool = True,
              paises: frozenset[str] | None = frozenset()) -> list[Hallazgo]:
    """Devuelve los identificadores encontrados, sin solapamientos."""
    hallazgos = estructurales(texto, paises, validar) + contextuales(texto)
    if agresivo:
        hallazgos += agresivos(texto)

    # Resolver solapamientos: prioridad estructural > contextual > agresiva, luego el más largo.
    prioridad = {"estructural": 0, "contextual": 1, "agresiva": 2}
    hallazgos.sort(key=lambda h: (prioridad[h.capa], -(h.fin - h.inicio), h.inicio))
    elegidos: list[Hallazgo] = []
    for h in hallazgos:
        if all(h.fin <= e.inicio or h.inicio >= e.fin for e in elegidos):
            elegidos.append(h)
    return sorted(elegidos, key=lambda h: h.inicio)


def anonimizar(texto: str, agresivo: bool = False, formato: str = "[{etiqueta}]") -> str:
    """Reemplaza cada identificador por formato.format(etiqueta=...)."""
    out, pos = [], 0
    for h in encontrar(texto, agresivo=agresivo):
        out.append(texto[pos:h.inicio])
        out.append(formato.format(etiqueta=h.etiqueta))
        pos = h.fin
    out.append(texto[pos:])
    return "".join(out)
