"""Benchmark de lotes: tiempo total según la cantidad de procesos de extracción.

Uso:
    python scripts/bench_batch.py                 # PDFs con texto + escaneados (si hay Tesseract)
    python scripts/bench_batch.py --docs 12 --workers 1 2 3

Usa sólo documentos ficticios generados con scripts/make_samples.py (requiere reportlab).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import make_samples  # noqa: E402
from anonymizer import ocr  # noqa: E402
from api import Api  # noqa: E402


def make_docs(folder: Path, docs: int) -> tuple[list[Path], list[Path]]:
    import pdfplumber

    text = []
    for n in range(docs):
        path = folder / f"texto_{n}.pdf"
        (make_samples.epicrisis_es if n % 2 == 0 else make_samples.lab_report_en)(path)
        text.append(path)
    with pdfplumber.open(text[0]) as pdf:
        images = [p.to_image(resolution=110).original.convert("RGB") for p in pdf.pages]
    scanned = []
    for n in range(docs):
        path = folder / f"escaneado_{n}.pdf"
        images[0].save(path, save_all=True, append_images=images[1:] + [images[0]])
        scanned.append(path)
    return text, scanned


def run(paths: list[Path], options: dict) -> float:
    api = Api()
    try:
        start = time.perf_counter()
        job = api.start_batch([{"path": str(p)} for p in paths], options)
        while not api.get_job(job["job_id"])["done"]:
            time.sleep(0.02)
        state = api.get_job(job["job_id"])
        assert all(i["status"] == "done" for i in state["items"]), state["items"]
        return time.perf_counter() - start
    finally:
        api.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=int, default=8)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 3])
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        text, scanned = make_docs(Path(tmp), args.docs)
        scenarios = [(f"{args.docs} PDFs con texto", text, {})]
        if ocr.TESSERACT in ocr.available_engines():
            scenarios.append((f"{args.docs} PDFs escaneados (3 págs, OCR Tesseract)", scanned,
                              {"ocr_mode": "force", "ocr_engine": "tesseract"}))
        for name, paths, options in scenarios:
            print(name)
            base = None
            for workers in args.workers:
                elapsed = run(paths, {**options, "max_workers": workers})
                base = base or elapsed
                print(f"  {workers} proceso(s): {elapsed:6.2f} s   x{base / elapsed:4.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
