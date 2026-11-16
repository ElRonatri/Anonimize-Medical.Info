"""Aho-Corasick (anonymizer.fastmatch) y paridad con el motor de regex."""

from __future__ import annotations

import random
import sys
import unicodedata
from pathlib import Path

import pytest

from anonymizer import anonymize_document, detector, fastmatch, load_text

pytestmark = pytest.mark.skipif(not fastmatch.AVAILABLE, reason="pyahocorasick no instalado")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def engine():
    """Restaura el motor por defecto después de cada prueba."""
    previous = detector.literal_engine()
    yield detector.set_literal_engine
    detector.set_literal_engine(previous)


# --------------------------------------------------------------------------- plegado

@pytest.mark.parametrize("text", [
    "José MUÑOZ Peña", "İstanbul ß ﬁ Æ ǅ", "emoji 🩺 y 𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "tab\tnbsp nl\n",
    "".join(chr(c) for c in range(0x20, 0x2FF)),
])
def test_fold_preserves_length(text):
    assert len(fastmatch.fold(text)) == len(text)


def test_fold_is_case_and_accent_insensitive():
    assert fastmatch.fold("JOSÉ Muñoz-Peña/Ç") == "jose munoz/pena/c"
    assert fastmatch.fold_key("  Johnson,  Robert   L. ") == "johnson robert l/"


def _span(matcher, text):
    return [(text[s:e], [p for p in payloads]) for s, e, payloads in matcher.finditer(text)]


def test_text_matcher_gaps_boundaries_and_overlaps():
    m = fastmatch.TermMatcher()
    for term in ("Johnson Robert L.", "Robert", "Ana"):
        m.add(term, term)
    m.build()
    text = "Paciente: JOHNSON,  Robert L. y Robertson; Ana-María, ANA"
    found = _span(m, text)
    assert ("JOHNSON,  Robert L.", ["Johnson Robert L."]) in found  # comas y espacios múltiples
    assert ("Robert", ["Robert"]) in found  # solapada: la resolución elige luego la más larga
    assert not any(t == "Robert" and "Robertson" in t for t, _ in found)
    assert [t for t, p in found if p == ["Ana"]] == ["Ana", "ANA"]  # "Ana-María": "-" no es letra


def test_digit_matcher_ignores_separators():
    m = fastmatch.TermMatcher(digits=True)
    m.add("12.345.678-5", "rut")
    m.build()
    text = "RUT 12345678-5, también 12 345 678 5 y 12.345.678-5; no 112.345.678-5 ni 12.345.678-59"
    assert [text[s:e] for s, e, _ in m.finditer(text)] == ["12345678-5", "12 345 678 5", "12.345.678-5"]


def test_positions_map_back_after_many_gaps():
    m = fastmatch.TermMatcher()
    m.add("Pérez", "x")
    m.build()
    text = "a,  b ,c   d,,e  " * 50 + "Sr. PEREZ."
    (start, end, _), = list(m.finditer(text))
    assert text[start:end] == "PEREZ"


# --------------------------------------------------------------------------- paridad

def _run(text, options, eng, engine):
    engine(eng)
    return anonymize_document(load_text(text), options)


def test_engines_selectable(engine):
    for name in ("regex", "aho", "auto"):
        engine(name)
        assert detector.literal_engine() == name
    with pytest.raises(ValueError):
        engine("otro")


def test_auto_engine_threshold(engine):
    engine("auto")
    few = detector.build_knowledge("Nombre: Ana Ruiz", detector.Options())
    assert few.term_matcher is None and few.digit_matcher is None
    letters = "abcdefghijklmnopqrstuvwxyz"
    names = "\n".join(f"Paciente: Nombre{letters[i % 26]}{letters[i // 26]} Apellido{letters[i % 26]}x"
                       for i in range(80))
    many = detector.build_knowledge(names, detector.Options())
    assert many.term_matcher is not None


def _dirty(rnd, text):
    """Variantes que el motor debe tolerar igual que la regex."""
    out = []
    for word in text.split(" "):
        r = rnd.random()
        if r < 0.15:
            word = word.upper()
        elif r < 0.25:
            word = "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))
        out.append(word)
        # Huecos que la regex `,?\s+` también admite (con « , » Aho-Corasick es más tolerante;
        # ver test_space_before_comma_is_tolerated).
        out.append(rnd.choice([" ", " ", " ", "  ", ", ", ",   ", "\t"]))
    return "".join(out)


@pytest.mark.parametrize("seed", range(12))
def test_random_documents_same_output_with_both_engines(seed, engine):
    import bench

    rnd = random.Random(seed)
    lines = bench.names_document(rnd.randint(5, 60), seed=seed).split("\n")
    text = "\n".join(_dirty(rnd, line) if rnd.random() < 0.5 else line for line in lines)
    options = rnd.choice([{}, {"output_format": "text"}, {"region": "CL", "aggressive_numbers": True},
                          {"replacement_style": "tag", "custom_terms": ["Soto Díaz", "Contreras"]}])
    regex = _run(text, options, "regex", engine)
    aho = _run(text, options, "aho", engine)
    assert aho["text"] == regex["text"]
    assert aho["entities"] == regex["entities"]


def test_space_before_comma_is_tolerated(engine):
    """Mejora documentada: «Pérez , Juan» (típico de OCR) se reconoce como un solo nombre."""
    text = "Nombre: Juan Carlos Pérez\nControl de PÉREZ , JUAN CARLOS sin novedad."
    aho = _run(text, {"output_format": "text"}, "aho", engine)["text"]
    regex = _run(text, {"output_format": "text"}, "regex", engine)["text"]
    assert "Control de [PACIENTE_1] sin novedad" in aho
    assert "PÉREZ" not in regex and "JUAN" not in regex  # la regex también oculta, pero en partes


@pytest.mark.parametrize("eng", ["regex", "aho"])
def test_ocr_glued_fields_are_still_hidden(eng, engine):
    """El OCR pega campos vecinos: el valor debe ocultarse igual (detectado en scripts/eval_ocr.py)."""
    text = ("Fecha de nacimiento: 21/08/1985Edad: 39 años\nFicha clínica: 778201Previsión: FONASA B\n"
            "Control 21/08/1985 y ficha 778201. Hb 12.8 g/dL.")
    out = _run(text, {"output_format": "text", "region": "all"}, eng, engine)["text"]
    assert "21/08/1985" not in out and "778201" not in out
    assert "Edad: 39 años" in out and "Previsión: FONASA B" in out and "12.8 g/dL" in out


@pytest.mark.parametrize("eng", ["regex", "aho"])
def test_names_keep_strict_word_boundary(eng, engine):
    out = _run("Nombre: Rosa Pérez\nVisita de Rosalía y Pérezgómez.", {"output_format": "text"}, eng, engine)["text"]
    assert "Rosalía" in out and "Pérezgómez" in out
