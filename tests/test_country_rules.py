"""Bloque 7: reglas por país en JSON y registro de validadores."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from anonymizer import country_rules, identifiers, validators
from anonymizer.country_rules import RuleError, parse_country

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def country(**overrides) -> dict:
    data = {
        "country": "Perú",
        "codes": ["PE"],
        "patterns": [{"label": "CE_PE", "name": "Carné de extranjería", "regex": "${B}CE-\\d{9}${E}"}],
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------- reglas incluidas

def test_bundled_rules_load_and_cover_previous_formats():
    rules = country_rules.load()
    labels = {p.label for p in rules.patterns}
    assert len(rules.patterns) >= 34
    assert {"RUN_CL", "CPF_BR", "CURP_MX", "DNI_ES", "NHS_UK", "MRZ", "EID_AE"} <= labels
    assert rules.country_codes["Internacional"] == ("*",)
    assert set(rules.regions) == {"latam", "north_america", "europe", "asia"}
    assert "pasaporte" in rules.keywords_ci and "CI" in rules.keywords_cs


def test_every_bundled_file_is_valid_json_with_known_fields():
    for path in sorted((country_rules.DATA_DIR / "countries").glob("*.json")):
        parse_country(json.loads(path.read_text(encoding="utf-8")), path.name)


def test_validators_are_resolved_from_registry():
    run = next(p for p in identifiers.ESTRUCTURALES if p.etiqueta == "RUN_CL")
    assert run.validador is validators.get("run_cl")
    assert run.validador("12.345.678-5") and not run.validador("12.345.678-9")


def test_macros_are_expanded():
    curp = next(p for p in identifiers.ESTRUCTURALES if p.etiqueta == "CURP_MX")
    assert "${" not in curp.regex and "|NE)" in curp.regex
    assert identifiers.anonimizar("CURP GODE561231HDFRRN09", agresivo=False) != "CURP GODE561231HDFRRN09"


def test_formats_by_country_for_ui():
    formats = identifiers.formatos_por_pais()
    assert formats["CL"] == ["RUN/RUT"]
    assert "Personnummer / CPR" in formats["DK"]


# --------------------------------------------------------------------------- errores claros

@pytest.mark.parametrize("data,message", [
    (country(codes=["peru"]), "codes"),
    (country(country=""), "country"),
    (country(extra=1), "campos desconocidos"),
    (country(patterns=[{"label": "ce_pe", "name": "x", "regex": "x"}]), ".label"),
    (country(patterns=[{"label": "CE_PE", "name": "x", "regex": "(abc"}]), "expresión regular inválida"),
    (country(patterns=[{"label": "CE_PE", "name": "x", "regex": "${NOPE}\\d"}]), "macro desconocida"),
    (country(patterns=[{"label": "CE_PE", "name": "x", "regex": "\\d", "validator": "nope"}]), "validador desconocido"),
    (country(patterns=[{"label": "CE_PE", "name": "x", "regex": "\\d", "flags": ["DOTALL"]}]), "opción desconocida"),
    (country(macros={"B": "x"}), "no se pueden redefinir"),
    (country(keywords={"xx": ["a"]}), "keywords"),
])
def test_invalid_rules_fail_with_location(data, message):
    with pytest.raises(RuleError) as err:
        parse_country(data, "pe.json")
    assert message in str(err.value) and "pe.json" in str(err.value)


def test_duplicate_pattern_across_files_is_rejected(tmp_path):
    dup = country(country="Chile", codes=["CL"],
                  patterns=[{"label": "RUN_CL", "name": "RUN/RUT", "regex": "\\d"}])
    (tmp_path / "cl2.json").write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(RuleError, match="duplicado"):
        country_rules.load([tmp_path])


def test_missing_extra_dir_is_reported(tmp_path):
    with pytest.raises(RuleError, match="no existe"):
        country_rules.load([tmp_path / "nada"])


# --------------------------------------------------------------------------- extensión sin tocar código

def test_extra_dir_adds_country_and_keywords(tmp_path):
    (tmp_path / "pe.json").write_text(json.dumps(country(keywords={"ci": ["carn[eé] de extranjer[ií]a pe"]})),
                                      encoding="utf-8")
    rules = country_rules.load([tmp_path])
    assert any(p.label == "CE_PE" and p.country == "Perú" for p in rules.patterns)
    assert rules.country_codes["Perú"] == ("PE",)
    assert "carn[eé] de extranjer[ií]a pe" in rules.keywords_ci


def test_new_country_via_env_var_end_to_end(tmp_path):
    """Un país nuevo (archivo JSON + validador de plugin) funciona sin modificar identifiers.py."""
    rule = country(patterns=[{"label": "CE_PE", "name": "Carné de extranjería",
                              "regex": "${B}CE-\\d{9}${E}", "validator": "luhn"}])
    (tmp_path / "pe.json").write_text(json.dumps(rule), encoding="utf-8")
    code = (
        f"import sys; sys.path.insert(0, {str(BACKEND)!r})\n"
        "from anonymizer import identifiers\n"
        "hits = identifiers.estructurales('Paciente CE-000000018 y CE-000000019', frozenset({'PE'}))\n"
        "print([(h.texto, h.etiqueta) for h in hits])\n"
        "print(sorted(identifiers.resolver_region('PE')), identifiers.formatos_por_pais()['PE'])\n"
    )
    env = {**__import__("os").environ, country_rules.ENV_EXTRA_DIRS: str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    first, second = out.stdout.splitlines()
    assert first == "[('CE-000000018', 'CE_PE')]"  # el segundo no pasa Luhn
    assert second == "['PE'] ['Carné de extranjería']"


# --------------------------------------------------------------------------- registro de validadores

def test_register_rejects_duplicates_and_bad_keys():
    with pytest.raises(ValueError, match="ya registrado"):
        validators.register("run_cl")(lambda s: True)
    with pytest.raises(ValueError, match="inválida"):
        validators.register("Run-CL")
    assert "run_cl" in validators.names() and "mrz_cd" not in validators.names()


def test_register_and_use_custom_validator():
    @validators.register("test_always_true")
    def _always(s: str) -> bool:
        return True

    try:
        rule = country(patterns=[{"label": "CE_PE", "name": "x", "regex": "\\d", "validator": "test_always_true"}])
        assert parse_country(rule, "pe.json")[2][0].validator == "test_always_true"
    finally:
        validators._REGISTRY.pop("test_always_true")


def test_plugins_loaded_from_entry_points(monkeypatch):
    class EP:
        def __init__(self, name, target):
            self.name, self._target = name, target

        def load(self):
            if isinstance(self._target, Exception):
                raise self._target
            return self._target

    eps = [EP("plugin_ok", lambda s: s.isdigit()), EP("plugin_broken", ImportError("x")), EP("plugin_bad", 42)]
    monkeypatch.setattr(validators.metadata, "entry_points", lambda group: eps)
    try:
        assert validators.load_plugins() == ["plugin_ok"]  # los defectuosos se omiten sin detener la app
        assert validators.get("plugin_ok")("123")
    finally:
        validators._REGISTRY.pop("plugin_ok", None)
