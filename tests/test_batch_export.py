import base64
import json
import sys
import time
from pathlib import Path

import pytest

from anonymizer import anonymize_document, load_bytes, load_text, ocr
from anonymizer.exporters import export_bytes

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from api import Api  # noqa: E402

ES_TEXT = "Nombre: Juan Pérez\nRUT: 12.345.678-5\nEl Sr. Pérez consulta en Hospital San Juan de Dios.\n"


def wait(api, job_id, timeout=60):
    known, results = [], {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = api.get_job(job_id, known)
        results.update(state["results"])
        known = list(results)
        if state["done"]:
            return state, results
        time.sleep(0.05)
    raise TimeoutError


@pytest.fixture()
def pdfs(tmp_path):
    pytest.importorskip("reportlab")
    import make_samples

    es, en = tmp_path / "epicrisis.pdf", tmp_path / "lab.pdf"
    make_samples.epicrisis_es(es)
    make_samples.lab_report_en(en)
    return es, en


def test_batch_processes_queue_in_background(pdfs, tmp_path):
    es, en = pdfs
    bad = tmp_path / "roto.pdf"
    bad.write_bytes(b"%PDF-1.4 esto no es un pdf")
    api = Api()
    started = time.perf_counter()
    res = api.start_batch([{"path": str(es)}, {"name": en.name, "data": base64.b64encode(en.read_bytes()).decode()},
                           {"path": str(bad)}, {"path": str(tmp_path / "no_existe.pdf")}], {})
    assert res["ok"] and len(res["items"]) == 4
    assert time.perf_counter() - started < 0.5  # la llamada no espera al procesamiento
    state, results = wait(api, res["job_id"])
    status = {i["name"]: i["status"] for i in state["items"]}
    assert status == {"epicrisis.pdf": "done", "lab.pdf": "done", "roto.pdf": "error", "no_existe.pdf": "error"}
    assert len(results) == 2
    assert all("ROJAS" not in r["text"] and "Johnson" not in r["text"] for r in results.values())
    # Los resultados ya entregados no se repiten
    assert api.get_job(res["job_id"], list(results))["results"] == {}


def test_reprocess_uses_cached_documents(pdfs):
    es, _ = pdfs
    api = Api()
    job = api.start_batch([{"path": str(es)}], {})
    _, results = wait(api, job["job_id"])
    item_id = next(iter(results))
    assert "Valenzuela" in results[item_id]["text"]
    again = api.reprocess({"anonymize_professionals": True})
    assert "Valenzuela" not in again["results"][item_id]["text"]


def test_cancel_job(pdfs):
    es, _ = pdfs
    api = Api()
    job = api.start_batch([{"path": str(es)} for _ in range(20)], {})
    api.cancel_job(job["job_id"])
    state, _ = wait(api, job["job_id"])
    assert any(i["status"] == "cancelled" for i in state["items"])


def test_process_text_and_export_to_folder(tmp_path):
    api = Api()
    res = api.process_text(ES_TEXT, {})
    doc = {"id": res["item"]["id"], "name": "Epicrisis Juan Pérez.pdf", "text": res["result"]["text"],
           "edited": False, "meta": res["result"]}
    for fmt in ("md", "txt", "docx", "json"):
        (tmp_path / fmt).mkdir()
        out = api.export_to_folder(str(tmp_path / fmt), [doc, doc], fmt, {})
        assert out["ok"] and out["count"] == 2
        names = sorted(Path(p).name for p in out["written"])
        assert names[0].endswith(f"_anonimizado.{fmt}") and names[0] != names[1]
    # .txt se regenera como texto plano (sin sintaxis Markdown) si no se editó
    txt = next((tmp_path / "txt").iterdir()).read_text(encoding="utf-8")
    assert "**" not in txt and "[PACIENTE_1]" in txt
    # Una versión editada a mano se exporta tal cual
    edited = api.export_to_folder(str(tmp_path / "md"), [{**doc, "text": "EDITADO", "edited": True}], "txt", {})
    assert Path(edited["written"][0]).read_text(encoding="utf-8") == "EDITADO"
    generic = api.export_to_folder(str(tmp_path / "md"), [doc], "json", {}, generic_names=True)
    written = Path(generic["written"][0])
    assert written.name == "documento_01_anonimizado.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert "Juan" not in json.dumps(payload, ensure_ascii=False)  # ni texto ni nombre de archivo


def test_json_export_has_no_original_values():
    result = anonymize_document(load_text(ES_TEXT), {})
    payload = json.loads(export_bytes("json", result["text"], {**result, "name": "x.md"}))
    assert payload["entities"] and all(set(e) == {"placeholder", "category", "count"} for e in payload["entities"])
    assert "Pérez" not in json.dumps(payload, ensure_ascii=False)


def test_docx_export_structure():
    docx = pytest.importorskip("docx")
    import io

    md = "## TÍTULO\n\n- **Nombre:** [PACIENTE_1]\n\n| A | B |\n| --- | --- |\n| 1 | x \\| y |\n\n---\n\n*Página 2*\n"
    d = docx.Document(io.BytesIO(export_bytes("docx", md, {"format": "markdown"})))
    texts = [p.text for p in d.paragraphs]
    assert "TÍTULO" in texts and "Nombre: [PACIENTE_1]" in texts
    assert d.tables[0].cell(1, 1).text == "x | y"


def test_whitelist_terms_are_never_anonymized():
    result = anonymize_document(load_text(ES_TEXT), {"whitelist": ["San Juan de Dios"], "output_format": "text"})
    assert "Hospital San Juan de Dios" in result["text"]
    assert "Juan Pérez" not in result["text"] and "Sr. Pérez" not in result["text"]
    result = anonymize_document(load_text(ES_TEXT), {"whitelist": ["pérez"], "output_format": "text"})
    assert "Sr. Pérez" in result["text"]


@pytest.mark.skipif(not ocr.available(), reason="sin motor OCR instalado")
def test_ocr_on_scanned_pdf(pdfs, tmp_path):
    es, _ = pdfs
    import pdfplumber

    with pdfplumber.open(es) as pdf:
        image = pdf.pages[0].to_image(resolution=150).original.convert("RGB")
    scan = tmp_path / "scan.pdf"
    image.save(scan)
    steps = []
    doc = load_bytes(scan.name, scan.read_bytes(), progress=lambda i, n, s: steps.append(s))
    result = anonymize_document(doc, {})
    assert result["ocr_pages"] == 1 and "ocr" in steps
    assert "EPICRISIS" in result["text"]
    assert "ROJAS" not in result["text"] and "778201" not in result["text"]
    off = anonymize_document(load_bytes(scan.name, scan.read_bytes(), ocr_mode="off"), {})
    assert off["ocr_pages"] == 0
