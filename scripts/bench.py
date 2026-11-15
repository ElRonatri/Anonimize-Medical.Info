"""Benchmark del motor de anonimización con documentos sintéticos (datos ficticios).

Uso:
    python scripts/bench.py                  # todos los escenarios con el motor por defecto
    python scripts/bench.py --engine regex   # fuerza la búsqueda de nombres por regex
    python scripts/bench.py --engine aho     # fuerza Aho-Corasick (requiere pyahocorasick)
    python scripts/bench.py --engine auto    # Aho-Corasick sólo si hay muchos valores (por defecto)
    python scripts/bench.py --compare        # compara los tres y verifica salida idéntica

Escenarios:
    dense   ~1,3 M caracteres de evolución clínica con pocos nombres (caso habitual)
    names   registro de N pacientes + narrativa que los menciona (muchos nombres distintos)
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from anonymizer import anonymize_document, detector, load_text  # noqa: E402

FIRST = ["Juan", "María", "José", "Ana", "Luis", "Carmen", "Pedro", "Lucía", "Jorge", "Sofía", "Andrés",
         "Valentina", "Diego", "Camila", "Matías", "Isabel", "Tomás", "Fernanda", "Ignacio", "Paula",
         "Thomas", "Emily", "Robert", "Sarah", "William", "Olivia", "James", "Grace", "Henry", "Chloe"]
LAST = ["Pérez", "González", "Muñoz", "Rojas", "Díaz", "Soto", "Contreras", "Silva", "Martínez", "Sepúlveda",
        "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres", "Araya", "Flores", "Espinoza",
        "Valenzuela", "Castillo", "Tapia", "Reyes", "Gutiérrez", "Castro", "Pizarro", "Álvarez", "Vásquez",
        "Sánchez", "Fernández", "Ramírez", "Carrasco", "Cortés", "Herrera", "Núñez", "Jara", "Vergara",
        "Rivera", "Figueroa", "Riquelme", "Miranda", "Bravo", "Vera", "Molina", "Vega", "Campos", "Sandoval",
        "Orellana", "Cárdenas", "Olivares", "Smith", "Johnson", "Brown", "Taylor", "Wilson", "Anderson"]


def dense_document() -> str:
    head = ("Nombre: JOSÉ ANTONIO MUÑOZ PEÑA   RUT: 16.789.012-3\nFecha de nacimiento: 14/02/1958\n"
            "Médico tratante: Dra. Carolina Ibáñez Reyes\n")
    body = "\n".join(
        f"Día {i}: Paciente estable, Hb {i % 15}.2 g/dL, PA 120/80. Sr. Muñoz refiere mejoría. "
        f"Control con Dra. Ibáñez." for i in range(60))
    return "\f".join([head + body] * 200)


def names_document(patients: int, seed: int = 7) -> str:
    rnd = random.Random(seed)
    people = []
    for _ in range(patients):
        people.append((rnd.choice(FIRST), rnd.choice(FIRST), rnd.choice(LAST), rnd.choice(LAST)))
    registry = "\n".join(f"Paciente: {f1} {f2} {l1} {l2}   RUT: {rnd.randint(5, 25)}.{rnd.randint(100, 999)}."
                         f"{rnd.randint(100, 999)}-{rnd.randint(0, 9)}" for f1, f2, l1, l2 in people)
    notes = []
    for i in range(patients * 4):
        f1, _, l1, _ = rnd.choice(people)
        notes.append(f"Nota {i}: el Sr. {l1} evoluciona bien; {f1} refiere dolor leve. Hb 12.{i % 10} g/dL, "
                     f"FC {60 + i % 40} lpm. Se indica paracetamol 1 g cada 8 horas por 3 días.")
    return registry + "\n\n" + "\n".join(notes)


def timeit(doc, options, repeat: int) -> tuple[float, dict]:
    times, result = [], {}
    for _ in range(repeat):
        start = time.perf_counter()
        result = anonymize_document(doc, options)
        times.append(time.perf_counter() - start)
    return min(times), result


def run(engine: str | None, repeat: int, scenarios: list[tuple[str, str, dict]]) -> dict[str, tuple[float, dict]]:
    if engine:
        detector.set_literal_engine(engine)
    out = {}
    for name, text, options in scenarios:
        doc = load_text(text)
        best, result = timeit(doc, options, repeat)
        out[name] = (best, result)
        n_lits = len(detector.build_knowledge(doc.full_text(), detector.Options.from_dict(options)).literals)
        print(f"  {name:<22} {len(text):>9,} car. {n_lits:>6} literales  {best * 1000:9.1f} ms  "
              f"{result['replacements']:>6} reemplazos")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["regex", "aho", "auto"], default=None)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()

    scenarios = [
        ("dense (1 paciente)", dense_document(), {"region": "all", "anonymize_professionals": True}),
        ("names 20 pacientes", names_document(20), {}),
        ("names 100 pacientes", names_document(100), {}),
        ("names 500 pacientes", names_document(500), {}),
        ("names 2000 pacientes", names_document(2000), {}),
    ]
    engines = ["regex", "aho", "auto"] if args.compare else [args.engine]
    results = {}
    for engine in engines:
        print(f"Motor de nombres: {engine or detector.literal_engine()}")
        results[engine] = run(engine, args.repeat, scenarios)
    if args.compare:
        print("\nAceleración respecto de regex y verificación de salida idéntica:")
        print(f"  {'escenario':<22} {'aho':>7} {'auto':>7}   salida")
        ok = True
        for name, *_ in scenarios:
            t_re, r_re = results["regex"][name]
            same = all(results[e][name][1]["text"] == r_re["text"]
                       and results[e][name][1]["entities"] == r_re["entities"] for e in ("aho", "auto"))
            ok &= same
            print(f"  {name:<22} x{t_re / results['aho'][name][0]:6.2f} x{t_re / results['auto'][name][0]:6.2f}"
                  f"   {'idéntica' if same else 'DIFERENTE'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
