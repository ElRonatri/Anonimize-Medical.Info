"""Bloque 7: textos de la interfaz en JSON (frontend/src/locales)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
LOCALES = FRONTEND / "src" / "locales"
PLURAL = {"zero", "one", "two", "few", "many", "other"}
PLACEHOLDER = re.compile(r"\{(\d+)\}")


def load(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def is_plural(value) -> bool:
    return isinstance(value, dict) and "other" in value and set(value) <= PLURAL


def flatten(tree: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and not is_plural(value):
            out.update(flatten(value, path + "."))
        else:
            out[path] = value
    return out


def placeholders(value) -> set[str]:
    texts = value.values() if is_plural(value) else [value]
    return {m for t in texts for m in PLACEHOLDER.findall(t)}


ES, EN = flatten(load("es")), flatten(load("en"))


def test_languages_have_the_same_keys():
    assert set(ES) == set(EN), {"solo_es": sorted(set(ES) - set(EN)), "solo_en": sorted(set(EN) - set(ES))}


@pytest.mark.parametrize("key", sorted(ES))
def test_same_shape_and_placeholders(key):
    es, en = ES[key], EN[key]
    assert is_plural(es) == is_plural(en), key
    for value in (es, en):
        texts = value.values() if is_plural(value) else [value]
        assert all(isinstance(t, str) and t.strip() for t in texts), key
    assert placeholders(es) == placeholders(en), key


def test_plurals_have_other_and_use_first_argument():
    for flat in (ES, EN):
        for key, value in flat.items():
            if is_plural(value):
                assert "0" in placeholders(value), key


def test_every_key_used_in_code_exists():
    used: set[str] = set()
    prefixes: set[str] = set()
    for path in (FRONTEND / "src").rglob("*.js*"):
        code = path.read_text(encoding="utf-8")
        used |= set(re.findall(r"\bt\(\s*'([\w.]+)'", code))
        prefixes |= set(re.findall(r"\bt\(\s*`([\w.]+)\.\$\{", code))
        # Claves pasadas como datos: { key: 'responsibleLocal', ... }
        used |= {k for k in re.findall(r"\bkey:\s*'([\w.]+)'", code) if k[0].islower()}
    missing = sorted(k for k in used if k not in ES)
    assert not missing, missing
    for prefix in prefixes:
        assert any(k.startswith(prefix + ".") for k in ES), prefix


def test_no_code_in_translations():
    raw = (LOCALES / "es.json").read_text(encoding="utf-8") + (LOCALES / "en.json").read_text(encoding="utf-8")
    assert "=>" not in raw and "${" not in raw


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no disponible")
def test_format_message_in_node():
    script = """
      const { formatMessage, isPlural } = await import(process.argv[1]);
      const p = { one: '{0} archivo', other: '{0} archivos' };
      const out = [
        formatMessage(p, 'es', [1]), formatMessage(p, 'es', [3]), formatMessage(p, 'en', [0]),
        formatMessage('Procesando {0} de {1}', 'es', [2, 9]), formatMessage('sin {0}', 'es', []),
        isPlural({ one: 'a', other: 'b' }), isPlural({ ok: 'a', other: 'b' }),
      ];
      console.log(JSON.stringify(out));
    """
    url = (FRONTEND / "src" / "format.js").as_uri()
    res = subprocess.run(["node", "--input-type=module", "-e", script, url],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["1 archivo", "3 archivos", "0 archivos", "Procesando 2 de 9",
                                      "sin {0}", True, False]
