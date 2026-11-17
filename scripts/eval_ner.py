"""Evalúa la segunda pasada NER con notas clínicas sintéticas (datos ficticios).

Mide, para cada modelo y umbral:
  * cobertura: nombres SIN etiqueta («acude con su hija X») ocultados por completo;
  * falsos positivos: términos clínicos en mayúscula («Diabetes Mellitus», «Enfermedad de
    Parkinson», «Servicio de Urgencia») que se ocultaron por error.

Uso (requiere la variante NER: pip install -r requirements-ner.txt):
    python scripts/eval_ner.py
    python scripts/eval_ner.py --models xx_ent_wiki_sm es_core_news_sm --thresholds 0.5 0.8 0.95
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from anonymizer import anonymize_document, load_text, ner  # noqa: E402

ES_FIRST = ["Bernardita", "Ignacio", "Constanza", "Rodrigo", "Macarena", "Sebastián", "Francisca",
            "Joaquín", "Josefina", "Cristóbal", "Trinidad", "Benjamín", "Antonia", "Vicente", "Catalina"]
ES_LAST = ["Quiroga", "Fuentealba", "Echeverría", "Undurraga", "Larraín", "Aravena", "Manríquez",
           "Valdebenito", "Sepúlveda", "Zúñiga", "Bustamante", "Cifuentes", "Saavedra", "Ossandón"]
EN_FIRST = ["Margaret", "Theodore", "Abigail", "Harrison", "Penelope", "Nathaniel", "Genevieve",
            "Fitzgerald", "Rosalind", "Barnaby", "Josephine", "Montgomery"]
EN_LAST = ["Whitfield", "Abernathy", "Kowalczyk", "Pemberton", "Okonkwo", "Fairbanks", "Lindqvist",
           "Castellano", "Hargreaves", "Delacroix", "Brennan", "Thornbury"]

ES_TEMPLATES = [
    "Paciente acude acompañada de su hija {n}.",
    "Se conversa con su esposo {n}, quien refiere buena adherencia.",
    "Llamado telefónico a {n} para coordinar el control.",
    "Evaluado en conjunto con el kinesiólogo {n}.",
    "Durante la visita, {n} relata episodios de dolor nocturno.",
    "Queda a cargo de su sobrina {n} al alta.",
]
EN_TEMPLATES = [
    "Patient arrived with her daughter {n}.",
    "Discussed the plan with his wife {n}, who agrees.",
    "Phone call to {n} to schedule follow-up.",
    "Seen together with physical therapist {n}.",
    "During the visit, {n} reported nocturnal pain.",
    "Will be cared for by her nephew {n} after discharge.",
]
ES_DISTRACTORS = [
    ("Antecedentes de Diabetes Mellitus tipo 2 e Hipertensión Arterial.",
     ["Diabetes Mellitus", "Hipertensión Arterial"]),
    ("Se diagnostica Enfermedad de Parkinson en etapa inicial.", ["Parkinson"]),
    ("Linfoma de Hodgkin en remisión completa.", ["Hodgkin"]),
    ("Enfermedad de Crohn controlada.", ["Crohn"]),
    ("Ingresa por el Servicio de Urgencia.", ["Servicio de Urgencia"]),
    ("Control en Policlínico de Cardiología.", ["Cardiología"]),
    ("Se indica Paracetamol 1 g cada 8 horas.", ["Paracetamol"]),
    ("Escala de Glasgow 15 al ingreso.", ["Glasgow"]),
    ("Insuficiencia Cardiaca Crónica descompensada.", ["Insuficiencia Cardiaca"]),
]
EN_DISTRACTORS = [
    ("History of Diabetes Mellitus and Hypertension.", ["Diabetes Mellitus", "Hypertension"]),
    ("Diagnosed with Parkinson disease last year.", ["Parkinson"]),
    ("Hodgkin Lymphoma in remission.", ["Hodgkin"]),
    ("Crohn disease is controlled.", ["Crohn"]),
    ("Admitted through the Emergency Department.", ["Emergency Department"]),
    ("Started on Acetaminophen 1 g every 8 hours.", ["Acetaminophen"]),
    ("Glasgow Coma Scale 15 on arrival.", ["Glasgow"]),
    ("Chronic Heart Failure exacerbation.", ["Heart Failure"]),
]


def dataset(lang: str, notes: int, seed: int = 11) -> tuple[str, list[str], list[str]]:
    rnd = random.Random(seed)
    first, last, templates, distractors = (
        (ES_FIRST, ES_LAST, ES_TEMPLATES, ES_DISTRACTORS) if lang == "es"
        else (EN_FIRST, EN_LAST, EN_TEMPLATES, EN_DISTRACTORS))
    lines, names, terms = [], [], []
    for _ in range(notes):
        name = f"{rnd.choice(first)} {rnd.choice(last)}"
        names.append(name)
        sentence, protected = rnd.choice(distractors)
        terms.extend(protected)
        lines.append(f"{rnd.choice(templates).format(n=name)} {sentence}")
    return "\n".join(lines), names, terms


def evaluate(text: str, names: list[str], terms: list[str], options: dict) -> tuple[float, int, dict]:
    result = anonymize_document(load_text(text), {"output_format": "text", **options})
    out = result["text"]
    hidden = sum(1 for n in names if not any(part in out for part in n.split()))
    false_positives = sum(1 for t in set(terms) if t not in out)
    return hidden / len(names), false_positives, result.get("ner", {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", type=int, default=60)
    parser.add_argument("--models", nargs="+", default=None, help="por defecto, los instalados")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.5, 0.8, 0.95])
    args = parser.parse_args()

    installed = [m for m in ("es_core_news_sm", "xx_ent_wiki_sm", "en_core_web_sm") if ner._installed(m)]
    models = args.models or installed
    for lang in ("es", "en"):
        text, names, terms = dataset(lang, args.notes)
        print(f"\n[{lang}] {len(names)} nombres sin etiqueta, {len(set(terms))} términos clínicos protegidos")
        print(f"  {'configuración':<40} {'cobertura':>10} {'falsos +':>9}")
        cov, fp, _ = evaluate(text, names, terms, {})
        print(f"  {'sólo reglas':<40} {cov * 100:9.1f}% {fp:>9}")
        for model in models:
            if lang == "en" and model == "es_core_news_sm" or lang == "es" and model == "en_core_web_sm":
                continue
            ner.MODELS[lang] = (model,)
            ner.available_models.cache_clear()
            for threshold in args.thresholds:
                opts = {"ner": True, "ner_threshold": threshold}
                cov, fp, _ = evaluate(text, names, terms, opts)
                print(f"  {f'{model} umbral {threshold}':<40} {cov * 100:9.1f}% {fp:>9}")
            original = ner.clinical_terms
            ner.clinical_terms = lambda: frozenset()  # type: ignore[assignment]
            try:
                cov, fp, _ = evaluate(text, names, terms, {"ner": True, "ner_threshold": 0.8})
            finally:
                ner.clinical_terms = original  # type: ignore[assignment]
            print(f"  {f'{model} umbral 0.8 SIN filtro clínico':<40} {cov * 100:9.1f}% {fp:>9}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
