"""Pruebas de regresión con "golden files".

Cada caso anonimiza un documento ficticio con unas opciones y compara la salida (texto y
resumen de entidades) con el archivo esperado en `tests/golden/`. Cualquier refactor del
motor debe reproducirla exactamente.

Para regenerar tras un cambio INTENCIONAL de comportamiento:
    UPDATE_GOLDEN=1 pytest tests/test_golden.py
y revisar el diff de `tests/golden/` antes de hacer commit.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from anonymizer import anonymize_document, load_bytes, load_text

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"

TEXT_CASES = {
    "es_default": ("es_epicrisis.txt", {}),
    "es_text_tag": ("es_epicrisis.txt", {"output_format": "text", "replacement_style": "tag"}),
    "es_full": ("es_epicrisis.txt", {"anonymize_professionals": True, "anonymize_all_dates": True,
                                     "region": "CL", "aggressive_numbers": True}),
    "es_whitelist_custom": ("es_epicrisis.txt", {"whitelist": ["Santa Rosa"], "custom_terms": ["Ñuñoa"],
                                                 "exclude": ["Rosa Peña Soto"]}),
    "es_as_english": ("es_epicrisis.txt", {"language": "en", "anonymize_addresses": False}),
    "en_default": ("en_discharge.txt", {}),
    "en_full": ("en_discharge.txt", {"anonymize_professionals": True, "region": "north_america",
                                     "anonymize_all_dates": True}),
    "ids_general": ("ids_mixed.txt", {"output_format": "text"}),
    "ids_all_regions": ("ids_mixed.txt", {"output_format": "text", "region": "all"}),
    "ids_latam_aggressive": ("ids_mixed.txt", {"output_format": "text", "region": "latam",
                                               "aggressive_numbers": True}),
}

PDF_CASES = {
    "pdf_es_default": ("epicrisis_es", {}),
    "pdf_es_full": ("epicrisis_es", {"anonymize_professionals": True, "region": "all"}),
    "pdf_en_text": ("lab_report_en", {"output_format": "text", "page_markers": False}),
}


def snapshot(result: dict) -> str:
    """Texto + resumen estable de entidades (sin tiempos de ejecución)."""
    lines = [result["text"].rstrip("\n"), "", "<!-- golden: entities -->"]
    for entity in result["entities"]:
        values = " | ".join(entity["values"])
        lines.append(f"{entity['placeholder']}\t{entity['category']}\t{entity['count']}\t{values}")
    lines.append(f"<!-- language={result['language']} pages={result['pages']} "
                 f"replacements={result['replacements']} -->")
    return "\n".join(lines) + "\n"


def check(name: str, result: dict) -> None:
    path = GOLDEN / f"{name}.golden.md"
    actual = snapshot(result)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"Falta {path.name}. Genera los golden files con UPDATE_GOLDEN=1 y revísalos.")
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"La salida de '{name}' cambió. Si es intencional, regenera con UPDATE_GOLDEN=1."


@pytest.mark.parametrize("name", sorted(TEXT_CASES))
def test_golden_text(name: str) -> None:
    fixture, options = TEXT_CASES[name]
    text = (FIXTURES / fixture).read_text(encoding="utf-8")
    check(name, anonymize_document(load_text(text), options))


@pytest.mark.parametrize("name", sorted(PDF_CASES))
def test_golden_pdf(name: str, tmp_path: Path) -> None:
    pytest.importorskip("reportlab")
    import make_samples

    builder, options = PDF_CASES[name]
    pdf = tmp_path / f"{builder}.pdf"
    getattr(make_samples, builder)(pdf)
    check(name, anonymize_document(load_bytes(pdf.name, pdf.read_bytes(), ocr_mode="off"), options))
