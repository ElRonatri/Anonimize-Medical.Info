"""Reglas de identificadores por país, cargadas desde archivos JSON.

Estructura (``data/identifiers/``)::

    countries/<código>.json   un archivo por país o grupo de países (formatos estructurales)
    contextual.json           palabras clave para la capa "palabra clave + valor"
    regions.json              regiones seleccionables en la interfaz -> códigos de país

Para añadir un país basta con un archivo nuevo en ``countries/`` (ver ``docs/reglas-por-pais.md``);
si su formato tiene dígito verificador, el validador se registra en ``validators.py`` o en un
plugin. También se pueden cargar reglas adicionales desde carpetas indicadas en la variable de
entorno ``ANONIMIZE_RULES_DIR`` (separadas por ``os.pathsep``), con el mismo formato.

Se usa JSON y no YAML para no añadir dependencias. Todo se valida al cargar: una regla mal
escrita falla con un mensaje que indica archivo y campo, en lugar de comportarse mal en silencio.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import validators

DATA_DIR = Path(__file__).resolve().parent / "data" / "identifiers"
ENV_EXTRA_DIRS = "ANONIMIZE_RULES_DIR"

# Macros disponibles en todas las expresiones: ${B} / ${E} = límites de token.
BUILTIN_MACROS = {
    "B": r"(?<![A-Za-z0-9])",
    "E": r"(?![A-Za-z0-9])",
}
FLAGS = {"IGNORECASE": re.IGNORECASE}

_MACRO_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_LABEL_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CODE_RE = re.compile(r"^(?:\*|[A-Z]{2})$")
_PATTERN_KEYS = {"label", "name", "regex", "validator", "flags"}
_COUNTRY_KEYS = {"country", "codes", "macros", "patterns", "keywords", "$comment"}


class RuleError(ValueError):
    """Regla inválida: el mensaje indica archivo y campo."""


@dataclass(frozen=True)
class PatternRule:
    label: str
    country: str
    name: str
    regex: str  # ya expandida (sin macros)
    validator: str | None = None
    flags: int = 0
    source: str = ""


@dataclass
class RuleSet:
    patterns: list[PatternRule] = field(default_factory=list)
    country_codes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    regions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    keywords_ci: list[str] = field(default_factory=list)
    keywords_cs: list[str] = field(default_factory=list)
    label_rules: list[tuple[str, str]] = field(default_factory=list)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuleError(f"{path.name}: no se pudo leer ({exc})") from exc


def _expect(cond: bool, where: str, msg: str) -> None:
    if not cond:
        raise RuleError(f"{where}: {msg}")


def _str_list(value: Any, where: str) -> list[str]:
    _expect(isinstance(value, list) and all(isinstance(v, str) and bool(v) for v in value),
            where, "debe ser una lista de textos no vacíos")
    return list(value)


def _compiles(regex: str, flags: int, where: str) -> None:
    try:
        re.compile(regex, flags)
    except re.error as exc:
        raise RuleError(f"{where}: expresión regular inválida ({exc})") from exc


def expand_macros(regex: str, macros: dict[str, str], where: str = "regex") -> str:
    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        _expect(name in macros, where, f"macro desconocida ${{{name}}}")
        return macros[name]

    return _MACRO_RE.sub(sub, regex)


def parse_country(data: Any, source: str) -> tuple[str, tuple[str, ...], list[PatternRule], dict[str, list[str]]]:
    """Valida un archivo de país. Devuelve (país, códigos, patrones, palabras clave)."""
    _expect(isinstance(data, dict), source, "debe ser un objeto JSON")
    unknown = set(data) - _COUNTRY_KEYS
    _expect(not unknown, source, f"campos desconocidos: {', '.join(sorted(unknown))}")
    country = data.get("country")
    _expect(isinstance(country, str) and bool(country.strip()), f"{source}: country", "falta el nombre del país")
    codes = tuple(_str_list(data.get("codes"), f"{source}: codes"))
    _expect(bool(codes) and all(_CODE_RE.match(c) for c in codes), f"{source}: codes",
            'deben ser códigos ISO 3166-1 alfa-2 en mayúsculas (o "*")')

    macros = dict(BUILTIN_MACROS)
    extra = data.get("macros", {})
    _expect(isinstance(extra, dict) and all(isinstance(v, str) for v in extra.values()),
            f"{source}: macros", "debe ser un objeto nombre -> texto")
    _expect(not set(extra) & set(BUILTIN_MACROS), f"{source}: macros", "no se pueden redefinir B ni E")
    macros.update(extra)

    raw_patterns = data.get("patterns", [])
    _expect(isinstance(raw_patterns, list), f"{source}: patterns", "debe ser una lista")
    patterns = []
    for i, p in enumerate(raw_patterns):
        where = f"{source}: patterns[{i}]"
        _expect(isinstance(p, dict), where, "debe ser un objeto")
        unknown = set(p) - _PATTERN_KEYS
        _expect(not unknown, where, f"campos desconocidos: {', '.join(sorted(unknown))}")
        label, name, regex = p.get("label"), p.get("name"), p.get("regex")
        _expect(isinstance(label, str) and bool(_LABEL_RE.match(label)), f"{where}.label",
                "MAYÚSCULAS, dígitos y _ (p. ej. RUN_CL)")
        _expect(isinstance(name, str) and bool(name.strip()), f"{where}.name", "falta el nombre")
        _expect(isinstance(regex, str) and bool(regex), f"{where}.regex", "falta la expresión")
        flags = 0
        for flag in _str_list(p.get("flags", []), f"{where}.flags"):
            _expect(flag in FLAGS, f"{where}.flags", f"opción desconocida {flag!r} (válidas: {', '.join(FLAGS)})")
            flags |= FLAGS[flag]
        validator = p.get("validator")
        if validator is not None:
            _expect(isinstance(validator, str), f"{where}.validator", "debe ser un texto")
            try:
                validators.get(validator)
            except KeyError as exc:
                raise RuleError(f"{where}.validator: {exc.args[0]}") from None
        expanded = expand_macros(regex, macros, f"{where}.regex")
        _compiles(expanded, flags, f"{where}.regex")
        patterns.append(PatternRule(label, country, name, expanded, validator, flags, source))

    keywords = data.get("keywords", {})
    _expect(isinstance(keywords, dict) and set(keywords) <= {"ci", "cs"}, f"{source}: keywords",
            'debe ser un objeto con "ci" y/o "cs"')
    kws = {k: _str_list(v, f"{source}: keywords.{k}") for k, v in keywords.items()}
    for k, values in kws.items():
        for kw in values:
            _compiles(kw, 0, f"{source}: keywords.{k}")
    return country, codes, patterns, kws


def _rule_dirs(extra: list[Path] | None) -> list[Path]:
    dirs = [DATA_DIR]
    env = os.environ.get(ENV_EXTRA_DIRS, "")
    dirs += [Path(p) for p in env.split(os.pathsep) if p.strip()]
    dirs += list(extra or [])
    return dirs


def load(extra_dirs: list[Path] | None = None) -> RuleSet:
    """Carga y valida las reglas incluidas más las de carpetas adicionales."""
    rules = RuleSet()
    seen: dict[tuple[str, str], str] = {}

    base_ctx = _read(DATA_DIR / "contextual.json")
    _expect(isinstance(base_ctx, dict), "contextual.json", "debe ser un objeto JSON")
    rules.keywords_ci = _str_list(base_ctx.get("keywords_ci"), "contextual.json: keywords_ci")
    rules.keywords_cs = _str_list(base_ctx.get("keywords_cs"), "contextual.json: keywords_cs")
    for i, r in enumerate(base_ctx.get("label_rules", [])):
        where = f"contextual.json: label_rules[{i}]"
        _expect(isinstance(r, dict) and isinstance(r.get("match"), str) and isinstance(r.get("label"), str)
                and bool(_LABEL_RE.match(r["label"])), where, 'debe tener "match" (regex) y "label"')
        _compiles(r["match"], 0, where)
        rules.label_rules.append((r["match"], r["label"]))

    regions = _read(DATA_DIR / "regions.json")
    _expect(isinstance(regions, dict), "regions.json", "debe ser un objeto región -> códigos")
    for region, codes in regions.items():
        codes = _str_list(codes, f"regions.json: {region}")
        _expect(all(_CODE_RE.match(c) and c != "*" for c in codes), f"regions.json: {region}",
                "códigos ISO 3166-1 alfa-2 en mayúsculas")
        rules.regions[region] = tuple(codes)

    for folder in _rule_dirs(extra_dirs):
        countries = folder / "countries" if (folder / "countries").is_dir() else folder
        if not countries.is_dir():
            raise RuleError(f"{folder}: la carpeta de reglas no existe")
        for path in sorted(countries.glob("*.json")):
            if folder != DATA_DIR and path.name in {"contextual.json", "regions.json"}:
                continue
            source = path.name if folder == DATA_DIR else str(path)
            country, codes, patterns, kws = parse_country(_read(path), source)
            previous = rules.country_codes.get(country)
            _expect(previous is None or previous == codes, source,
                    f"el país {country!r} ya está definido con otros códigos {previous}")
            rules.country_codes[country] = codes
            for p in patterns:
                key = (p.label, p.name)
                _expect(key not in seen, source, f"patrón duplicado {p.label} / {p.name} (ya en {seen.get(key)})")
                seen[key] = source
                rules.patterns.append(p)
            rules.keywords_ci += kws.get("ci", [])
            rules.keywords_cs += kws.get("cs", [])

    rules.keywords_ci = list(dict.fromkeys(rules.keywords_ci))
    rules.keywords_cs = list(dict.fromkeys(rules.keywords_cs))
    return rules
