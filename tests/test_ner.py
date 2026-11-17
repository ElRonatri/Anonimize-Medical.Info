"""Bloque 6: segunda pasada NER opcional (variante de build --ner)."""

from __future__ import annotations

import pytest

from anonymizer import anonymize_document, detector, load_text, ner

HAS_NER = ner.available("es")
needs_model = pytest.mark.skipif(not HAS_NER, reason="variante NER no instalada (requirements-ner.txt)")


def run(text: str, **options) -> dict:
    return anonymize_document(load_text(text), {"output_format": "text", **options})


# --------------------------------------------------------------------------- filtros (sin modelo)

@pytest.mark.parametrize("raw,expected", [
    ("Bernardita Quiroga", "Bernardita Quiroga"),
    ("Dra. Carolina Ibáñez Reyes", "Carolina Ibáñez Reyes"),
    ("Bernardita Quiroga sobre el control", "Bernardita Quiroga"),  # el modelo alarga la entidad
    ("Juan de la Fuente y", "Juan de la Fuente"),
    ("Ayer", None),  # una sola palabra: demasiado ambiguo
    ("Diabetes Mellitus", None),  # término clínico
    ("Enfermedad de Parkinson", None),  # epónimo
    ("Linfoma de Hodgkin", None),
    ("HTA DM", None),  # siglas
    ("Paciente Número 2", None),
    ("Ñuñoa Teléfono", None),  # palabras de etiqueta (vía stop)
    ("Médico tratante: Dra. Carolina Ibáñez Reyes", "Carolina Ibáñez Reyes"),  # tramo dentro del span
    ("Derivada desde el Servicio de Urgencia del Hospital del Salvador", None),
])
def test_clean_person(raw, expected):
    stop = frozenset(detector._NON_NAME_NORM)
    assert ner.clean_person(raw, stop) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Servicio de Urgencia del Hospital del Salvador", "Hospital del Salvador"),
    ("Clínica Las Condes", "Clínica Las Condes"),
    ("Servicio de Urgencia", None),
    ("Hospital Regional", None),  # sólo palabras genéricas
    ("HTA", None),
    ("Derivada desde el Servicio de Urgencia del Hospital del Salvador", "Hospital del Salvador"),
])
def test_clean_org(raw, expected):
    assert ner.clean_org(raw) == expected


def test_clinical_lexicon_loads_and_includes_eponyms():
    terms = ner.clinical_terms()
    assert len(terms) > 500
    assert {"parkinson", "hodgkin", "crohn", "diabetes", "paracetamol", "hypertension"} <= terms
    assert "hipertension" in terms  # sin tildes


def test_professional_tokens_from_rules():
    text = "Médico tratante: Dra. Carolina Ibáñez Reyes\nInterconsulta a Dr. Pedro Salinas."
    assert {"carolina", "ibanez", "reyes", "pedro", "salinas"} <= detector._professional_tokens(text)


def test_without_model_ner_option_is_a_noop(monkeypatch):
    monkeypatch.setattr(ner, "available", lambda lang=None: False)
    text = "Ayer se conversó con su hija Bernardita Quiroga."
    with_ner, without = run(text, ner=True), run(text)
    assert with_ner["text"] == without["text"]
    assert with_ner["ner"]["used"] is False


def test_ner_off_by_default():
    assert detector.Options().ner is False and detector.Options().ner_orgs is False


# --------------------------------------------------------------------------- con el modelo

UNLABELED = ("Paciente estable.\nAyer se conversó con su hija Bernardita Quiroga sobre el control.\n"
             "Médico tratante: Dra. Carolina Ibáñez Reyes\n"
             "Antecedentes de Diabetes Mellitus y Enfermedad de Parkinson.\n"
             "Derivada desde el Servicio de Urgencia del Hospital del Salvador.")


@needs_model
def test_ner_hides_unlabeled_names_only():
    rules_only = run(UNLABELED)["text"]
    assert "Bernardita" in rules_only  # las reglas no lo detectan
    result = run(UNLABELED, ner=True)
    out = result["text"]
    assert "Bernardita" not in out and "Quiroga" not in out
    for kept in ("Ayer", "control", "Diabetes Mellitus", "Parkinson", "Servicio de Urgencia"):
        assert kept in out, kept
    assert result["ner"]["used"] and result["ner"]["persons"] >= 1


@needs_model
def test_ner_respects_professionals_option():
    assert "Carolina Ibáñez Reyes" in run(UNLABELED, ner=True)["text"]
    assert "Ibáñez" not in run(UNLABELED, ner=True, anonymize_professionals=True)["text"]


@needs_model
def test_ner_organizations_are_optional():
    assert "Hospital del Salvador" in run(UNLABELED, ner=True)["text"]
    with_orgs = run(UNLABELED, ner=True, ner_orgs=True)
    assert "Hospital del Salvador" not in with_orgs["text"]
    assert "Servicio de Urgencia" in with_orgs["text"]  # parte genérica conservada
    assert any(e["category"] == "ORGANIZATION" for e in with_orgs["entities"])


def test_threshold_and_label_confusion(monkeypatch):
    """Umbral de confianza y entidades mal etiquetadas, con puntajes controlados (sin modelo)."""
    monkeypatch.setattr(ner, "available", lambda lang=None: True)
    monkeypatch.setattr(ner, "raw_entities", lambda text, lang: [
        ("Bernardita Quiroga", "PER", 0.95),
        ("Rodrigo Undurraga", "PER", 0.60),
        ("Servicio de Urgencia del Hospital del Salvador", "PER", 0.99),  # institución etiquetada PER
        ("Ayer", "PER", 1.0),
    ])
    found = {(e.text, e.label) for e in ner.find_entities("x", "es", threshold=0.8, orgs=True)}
    assert found == {("Bernardita Quiroga", "PERSON"), ("Hospital del Salvador", "ORG")}
    found = {(e.text, e.label) for e in ner.find_entities("x", "es", threshold=0.5, orgs=False)}
    assert found == {("Bernardita Quiroga", "PERSON"), ("Rodrigo Undurraga", "PERSON")}


@needs_model
def test_ner_respects_whitelist():
    assert "Bernardita Quiroga" in run(UNLABELED, ner=True, whitelist=["Bernardita Quiroga"])["text"]


@needs_model
def test_ner_english():
    out = run("Discussed the plan with his wife Penelope Whitfield.\nHistory of Diabetes Mellitus.",
              ner=True)["text"]
    assert "Penelope" not in out and "Whitfield" not in out and "Diabetes Mellitus" in out


@needs_model
def test_raw_entities_are_cached(monkeypatch):
    calls = []
    real = ner._scored_entities
    monkeypatch.setattr(ner, "_scored_entities", lambda nlp, text: calls.append(1) or real(nlp, text))
    text = "Texto único para la caché: conversación con Rodrigo Undurraga."
    ner.raw_entities(text, "es")
    ner.raw_entities(text, "es")
    assert len(calls) == 1


@needs_model
def test_ner_runs_with_network_blocked():
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent / "backend"
    code = (f"import sys; sys.path.insert(0, {str(backend)!r})\n"
            "from anonymizer.privacy import block_network; block_network()\n"
            "from anonymizer import anonymize_document, load_text\n"
            "r = anonymize_document(load_text('Se conversó con su hija Bernardita Quiroga.'), {'ner': True})\n"
            "assert 'Bernardita' not in r['text'], r['text']\nprint('ok')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr
