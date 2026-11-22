"""PDF censurado: misma página, datos tapados de forma irreversible."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

pdfium = pytest.importorskip("pypdfium2")
canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")

from anonymizer import load_bytes, load_text, ocr  # noqa: E402
from anonymizer.redact_pdf import ALLOWED_DPI, DEFAULT_DPI, redact_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = "Zxqwerty Vadremkuz Fuentes"
LINES = [
    ("Paciente: {name}", 700),
    ("RUT: 15.234.567-K", 680),
    ("Diagnostico: Neumonia adquirida en la comunidad.", 660),
    ("La paciente Vadremkuz evoluciona bien.", 640),
]


def make_pdf(name: str = NAME, *, title: str | None = None, annotation: str | None = None,
             rotation: int = 0, crop: tuple[float, float, float, float] | None = None,
             extra: list[tuple[str, int]] | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    c = canvas_mod.Canvas(buf, pagesize=A4)
    if title:
        c.setTitle(title)
    c.setFont("Helvetica", 14)
    for text, y in LINES + (extra or []):
        c.drawString(80, y, text.format(name=name))
    if annotation:
        c.textAnnotation(annotation, Rect=(400, 400, 500, 450))
    c.showPage()
    c.save()
    if not rotation and not crop:
        return buf.getvalue()
    doc = pdfium.PdfDocument(buf.getvalue())
    page = doc[0]
    if rotation:
        page.set_rotation(rotation)
    if crop:
        page.set_cropbox(*crop)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory) -> bytes:
    """Epicrisis ficticia de scripts/make_samples.py (samples/ no se versiona)."""
    import make_samples

    path = tmp_path_factory.mktemp("muestras") / "epicrisis_ejemplo.pdf"
    make_samples.epicrisis_es(path)
    return path.read_bytes()


def render(data: bytes, scale: float = 1.0):
    return pdfium.PdfDocument(data)[0].render(scale=scale, draw_annots=False).to_pil().convert("L")


def redact(data: bytes, **kwargs):
    doc = load_bytes("x.pdf", data, ocr_mode="off")
    return redact_pdf(data, doc, {"region": "CL"}, **kwargs)


def ink_difference(with_name: bytes, without_name: bytes) -> list[tuple[int, int]]:
    """Píxeles que pinta el nombre: diferencia entre la página con y sin él."""
    a, b = render(with_name), render(without_name)
    pa, pb = a.load(), b.load()
    return [(x, y) for x in range(a.width) for y in range(a.height) if pb[x, y] - pa[x, y] > 80]


# --------------------------------------------------------------------------- cobertura geométrica

@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [None, (40, 480, 520, 790)])
def test_name_ink_is_fully_covered(rotation, crop):
    """Con cualquier rotación y cropbox, cada píxel del nombre queda negro en el PDF censurado."""
    original = make_pdf(rotation=rotation, crop=crop)
    blank = make_pdf(name=" " * len(NAME), rotation=rotation, crop=crop)
    ink = ink_difference(original, blank)
    assert len(ink) > 50  # el nombre está en la página
    out, report = redact(original, dpi=DEFAULT_DPI, labels=False)
    red = render(out, scale=1.0)
    px = red.load()
    uncovered = [p for p in ink if px[min(p[0], red.width - 1), min(p[1], red.height - 1)] > 60]
    assert not uncovered, f"{len(uncovered)} píxeles del nombre sin tapar"
    assert report["unlocated"] == []
    assert red.size == render(original).size  # misma página, mismo tamaño


def test_clinical_text_is_not_covered():
    original = make_pdf()
    with_diag = render(original)
    blank = make_pdf(extra=[], name=NAME)
    out, _ = redact(blank, labels=False)
    red = render(out)
    # Franja de "Diagnostico: Neumonia..." (y = 660 en coordenadas PDF -> ~182 px desde arriba).
    band = red.crop((80, 170, 400, 186))
    assert sum(band.tobytes()) / (band.width * band.height) > 150  # mayormente blanco: no se tapó
    assert with_diag.size == red.size


# --------------------------------------------------------------------------- irreversibilidad

def test_output_has_no_text_metadata_or_annotations():
    data = make_pdf(title=f"Epicrisis {NAME}", annotation=f"Llamar a {NAME}")
    out, report = redact(data)
    doc = pdfium.PdfDocument(out)
    assert all(doc[i].get_textpage().get_text_range() == "" for i in range(len(doc)))
    assert b"Vadremkuz" not in out and "Vadremkuz".encode("utf-16-be") not in out
    assert "Vadremkuz" not in json.dumps(doc.get_metadata_dict(), ensure_ascii=False)
    assert report["annotations_removed"] >= 1
    assert "Vadremkuz" not in json.dumps(report)  # el informe nunca lleva valores


def test_sample_epicrisis_end_to_end(sample_pdf):
    data = sample_pdf
    out, report = redact(data)
    src, dst = pdfium.PdfDocument(data), pdfium.PdfDocument(out)
    assert len(dst) == len(src) == report["pages"]
    for i in range(len(src)):
        assert dst[i].get_size() == pytest.approx(src[i].get_size(), abs=1.0)
    assert report["redactions"] >= 10 and report["unlocated"] == [] and report["page_errors"] == []
    for value in (b"ROJAS", b"15.234.567", b"Acacias"):
        assert value not in out


# --------------------------------------------------------------------------- decisiones y opciones

def test_whitelist_is_respected():
    data = make_pdf(name="Rosa Perez Soto", extra=[("Derivada desde Clinica Santa Rosa.", 620)])
    doc = load_bytes("x.pdf", data, ocr_mode="off")
    out, _ = redact_pdf(data, doc, {"whitelist": ["Clinica Santa Rosa"]}, labels=False)
    red = render(out)
    # Línea de la clínica (y = 620 -> ~222 px desde arriba): sin recuadros negros.
    band = red.crop((80, 210, 420, 226))
    assert min(band.tobytes()) > 0 or sum(1 for p in band.tobytes() if p < 30) < 60


def test_labels_are_drawn_inside_boxes():
    data = make_pdf()
    with_labels, _ = redact(data, labels=True, dpi=300)
    without, _ = redact(data, labels=False, dpi=300)
    a, b = render(with_labels), render(without)
    box = (150, 125, 300, 145)  # zona del nombre en la línea "Paciente:"
    whites = sum(1 for p in a.crop(box).tobytes() if p > 150)
    assert whites > sum(1 for p in b.crop(box).tobytes() if p > 150)


def test_unlocated_values_are_reported_by_placeholder_only():
    data = make_pdf()
    doc = load_text(f"Paciente: {NAME}\nAcompañante: Bernarda Quiroga Lillo")  # no está en el PDF
    out, report = redact_pdf(data, doc, {})
    assert report["unlocated"] and all(u.startswith("[") for u in report["unlocated"])
    assert "Quiroga" not in json.dumps(report)


@pytest.mark.parametrize("dpi,expected", [(150, 150), (300, 300), (123, DEFAULT_DPI)])
def test_dpi_controls_image_resolution(dpi, expected):
    out, report = redact(make_pdf(), dpi=dpi)
    assert report["dpi"] == expected and expected in ALLOWED_DPI
    page = pdfium.PdfDocument(out)[0]
    image = next(o for o in page.get_objects() if isinstance(o, pdfium.PdfImage))
    width_px, _ = image.get_px_size()
    assert width_px == pytest.approx(page.get_width() * expected / 72, abs=2)


@pytest.mark.skipif("tesseract" not in ocr.available_engines(), reason="Tesseract no disponible")
def test_scanned_page_is_redacted_with_ocr_boxes():
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=34)
    for i, line in enumerate(["EPICRISIS", f"Paciente: {NAME}", "Diagnostico: Neumonia."]):
        draw.text((100, 120 + 70 * i), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=150)
    data = buf.getvalue()
    doc = load_bytes("scan.pdf", data, ocr_mode="force", ocr_engine="tesseract")
    out, report = redact_pdf(data, doc, {}, labels=False)
    assert report["ocr_pages"] == 1 and report["redactions"] >= 1 and report["unlocated"] == []
    red = render(out, scale=150 / 72)
    name_band = red.crop((300, 190, 800, 225))  # línea "Paciente: ..." en píxeles a 150 ppp
    assert sum(1 for p in name_band.tobytes() if p < 40) > 0.5 * name_band.width * name_band.height


# --------------------------------------------------------------------------- API

def test_api_exports_pdf_only_for_pdf_documents(tmp_path, monkeypatch, sample_pdf):
    import appdata
    from api import Api

    monkeypatch.setenv(appdata.ENV_DATA_DIR, str(tmp_path / "datos"))
    api = Api()
    sample = sample_pdf
    import base64
    import time

    job = api.start_batch([{"name": "epicrisis.pdf", "data": base64.b64encode(sample).decode()}], {})
    state = api.get_job(job["job_id"])
    while not state["done"]:
        time.sleep(0.05)
        state = api.get_job(job["job_id"])
    pdf_id = state["items"][0]["id"]
    text_id = api.process_text("Paciente: Juan Perez Soto", {})["item"]["id"]
    try:
        res = api.export_to_folder(str(tmp_path), [{"id": pdf_id, "name": "epicrisis.pdf"},
                                                   {"id": text_id, "name": "texto"}], "pdf", {"pdf_dpi": 150})
        assert res["ok"] and res["count"] == 1 and res["skipped"] == 1
        assert res["report"]["pages"] == 2 and res["report"]["unlocated"] == []
        written = Path(res["written"][0])
        assert written.suffix == ".pdf" and b"ROJAS" not in written.read_bytes()
        assert "pdf" in api.get_app_info()["export_formats"]
    finally:
        api.shutdown()


def test_pdf_prefs_are_allowed(tmp_path, monkeypatch):
    import appdata

    monkeypatch.setenv(appdata.ENV_DATA_DIR, str(tmp_path))
    store = appdata.PrefStore()
    store.set("options", {"pdf_dpi": 300, "pdf_labels": False})
    assert store.load()["options"] == {"pdf_dpi": 300, "pdf_labels": False}
    store.set("options", {"pdf_dpi": 123, "pdf_labels": "si"})
    assert store.load()["options"] == {}


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_text_export_of_rotated_pages_hides_the_name(rotation, monkeypatch):
    """Páginas con /Rotate: antes el texto salía desordenado o al revés y el nombre se filtraba."""
    from anonymizer import anonymize_document, extract

    data = make_pdf(rotation=rotation)
    text = anonymize_document(load_bytes("x.pdf", data, ocr_mode="off"), {})["text"]
    assert "Vadremkuz" not in text and "Paciente:" in text
    # Control negativo: sin leer la capa de texto desde la copia sin rotar, el nombre se filtra.
    monkeypatch.setattr(extract, "unrotated_copy", lambda _: None)
    leaked = anonymize_document(load_bytes("x.pdf", data, ocr_mode="off"), {})["text"]
    assert "Vadremkuz" in leaked or "zukmerdaV" in leaked  # a 180°/270° sale escrito al revés


def test_only_custom_words_in_redacted_pdf():
    """En el PDF censurado también se tapa exactamente la lista del usuario, y nada más."""
    data = make_pdf()
    doc = load_bytes("x.pdf", data, ocr_mode="off")
    out, report = redact_pdf(data, doc, {"custom_terms": ["vadremkuz"], "only_custom": True}, labels=False)
    assert report["redactions"] == 2 and report["unlocated"] == []  # línea del paciente y evolución
    out_all, report_all = redact_pdf(data, doc, {"region": "CL"}, labels=False)
    assert report_all["redactions"] > report["redactions"]  # en modo normal también RUT, nombre completo...
