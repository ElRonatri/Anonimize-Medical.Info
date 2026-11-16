"""Evalúa la precisión del OCR (y de modelos cuantizados) con documentos ficticios.

Renderiza los PDFs de ejemplo (scripts/make_samples.py) como imágenes y compara el texto
reconocido con el texto real del PDF: CER = distancia de edición / longitud del texto real
(0 % = perfecto). También mide el tamaño de los modelos y el tiempo por página.

Uso (requiere la variante OCR: pip install -r requirements-ocr.txt onnx):
    python scripts/eval_ocr.py                     # modelos originales (FP32)
    python scripts/eval_ocr.py --quantize          # + modelos int8 (det, rec y ambos)

La cuantización se hace en tiempo de build/evaluación con onnxruntime.quantization; la
aplicación nunca descarga ni convierte modelos.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def cer(reference: str, hypothesis: str) -> float:
    """Distancia de Levenshtein / len(referencia)."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0
    previous = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, hc in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (rc != hc))
        previous = current
    return previous[-1] / len(ref)


_TOKEN_RE = re.compile(r"[\w.\-/@]{2,}")

# Datos ficticios de los PDFs de ejemplo que NUNCA deben quedar visibles tras anonimizar.
SENSITIVE = ["ROJAS", "FERNANDA", "Rojas", "María", "15.234.567", "21/08/1985", "778201", "Acacias",
             "7123", "mf.rojas", "Pedro", "Johnson", "Robert", "55120934", "07/19/1958", "Oak Street", "555-0199"]


def token_recall(reference: str, hypothesis: str) -> float:
    """Fracción de palabras del texto real reconocidas (sin importar el orden de lectura)."""
    from collections import Counter

    ref = Counter(t.lower() for t in _TOKEN_RE.findall(normalize(reference)))
    hyp = Counter(t.lower() for t in _TOKEN_RE.findall(normalize(hypothesis)))
    total = sum(ref.values())
    return sum(min(n, hyp[t]) for t, n in ref.items()) / total if total else 1.0


def leaks(ocr_lines: list[str], truth: str) -> int:
    """Datos sensibles presentes en la página que siguen visibles tras anonimizar el texto OCR."""
    from anonymizer import anonymize_document, load_text

    out = anonymize_document(load_text("\n".join(ocr_lines)), {"region": "all"})["text"]
    present = [s for s in SENSITIVE if s in truth]
    return sum(1 for s in present if s in out)


def pages(folder: Path, dpis: tuple[int, ...]) -> list[tuple[str, object, str]]:
    import pdfplumber

    import make_samples

    out = []
    for builder in ("epicrisis_es", "lab_report_en"):
        pdf = folder / f"{builder}.pdf"
        getattr(make_samples, builder)(pdf)
        with pdfplumber.open(pdf) as document:
            for number, page in enumerate(document.pages, 1):
                truth = page.extract_text() or ""
                for dpi in dpis:
                    image = page.to_image(resolution=dpi).original.convert("RGB")
                    out.append((f"{builder} p{number} {dpi}dpi", image, truth))
    return out


def quantize(model: Path, target: Path) -> Path:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(str(model), str(target), weight_type=QuantType.QUInt8)
    return target


def evaluate(name: str, det: Path, rec: Path, cls: Path, samples) -> dict:
    import numpy as np
    from rapidocr import RapidOCR

    engine = RapidOCR(params={"Det.model_path": str(det), "Rec.model_path": str(rec),
                              "Cls.model_path": str(cls), "Global.log_level": "error"})
    errors, recalls, leaked, total_time = [], [], 0, 0.0
    for _label, image, truth in samples:
        start = time.perf_counter()
        result = engine(np.array(image))
        total_time += time.perf_counter() - start
        boxes = result.boxes if result.boxes is not None else []
        items = sorted(((float(min(p[1] for p in b)), float(min(p[0] for p in b)), t)
                        for b, t in zip(boxes, result.txts or [], strict=False)))
        text = " ".join(t for *_, t in items)
        errors.append(cer(truth, text))
        recalls.append(token_recall(truth, text))
        lines = _lines(items)
        leaked += leaks(lines, truth)
    size = sum(p.stat().st_size for p in (det, rec, cls)) / 1e6
    return {"name": name, "size_mb": size, "cer": sum(errors) / len(errors), "max_cer": max(errors),
            "recall": sum(recalls) / len(recalls), "leaks": leaked,
            "ms_per_page": total_time / len(samples) * 1000}


def _lines(items):
    """Agrupa las cajas por línea (como anonymizer.ocr) para que las etiquetas queden juntas."""
    lines: list[list] = []
    for y, x, t in items:
        if lines and abs(lines[-1][0][0] - y) < 12:
            lines[-1].append((y, x, t))
        else:
            lines.append([(y, x, t)])
    return ["   ".join(t for _, _, t in sorted(line, key=lambda i: i[1])) for line in lines]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quantize", action="store_true")
    parser.add_argument("--dpi", type=int, nargs="+", default=[110, 200])
    args = parser.parse_args()

    import rapidocr

    models = Path(rapidocr.__file__).resolve().parent / "models"
    det, rec, cls = (sorted(models.glob(p))[0] for p in ("*det*.onnx", "*rec*.onnx", "*cls*.onnx"))
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        samples = pages(tmpdir, tuple(args.dpi))
        configs = [("FP32 (original)", det, rec, cls)]
        if args.quantize:
            det8 = quantize(det, tmpdir / "det_int8.onnx")
            rec8 = quantize(rec, tmpdir / "rec_int8.onnx")
            configs += [("int8 det", det8, rec, cls), ("int8 rec", det, rec8, cls), ("int8 det+rec", det8, rec8, cls)]
        print(f"{len(samples)} páginas ({', '.join(f'{d} dpi' for d in args.dpi)}); CER = error por carácter")
        print(f"{'modelos':<18} {'tamaño':>9} {'CER':>8} {'palabras':>9} {'datos expuestos':>16} {'ms/pág':>8}")
        for name, d, r, c in configs:
            res = evaluate(name, d, r, c, samples)
            print(f"{res['name']:<18} {res['size_mb']:7.1f}MB {res['cer'] * 100:7.2f}% "
                  f"{res['recall'] * 100:8.2f}% {res['leaks']:>16} {res['ms_per_page']:8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
