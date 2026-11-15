from pathlib import Path

import pytest

from anonymizer import anonymize_document, load_bytes, load_text
from anonymizer.lang import detect_language

ES_TEXT = """HOSPITAL CLÍNICO SAN JOSÉ
EPICRISIS
Nombre: JUAN CARLOS PÉREZ GONZÁLEZ   RUT: 12.345.678-9   Edad: 54 años
Fecha de nacimiento: 03/04/1970   Sexo: Masculino
Ficha clínica N° 0045821
Dirección: Av. Los Leones 1234, Providencia
Teléfono: +56 9 8765 4321   Email: jcperez@gmail.com
Madre: María Gómez
Médico tratante: Dr. Roberto Soto Muñoz

ANAMNESIS
Paciente de 54 años, el Sr. Pérez consulta por dolor torácico.
Ingresa el 12/05/2024. Hemoglobina 13.5 g/dL, plaquetas 250.000.
Juan refiere tabaquismo. Controlar con Dr. Soto en 2 semanas.
"""

EN_TEXT = """DISCHARGE SUMMARY
Patient Name: Smith, John A.    MRN: 00482913    DOB: March 14, 1962
Address: 1452 Maple Avenue, Springfield, IL 62704
Phone: (217) 555-0143    SSN: 123-45-6789
Emergency Contact: Mary Smith
Attending Physician: Dr. Emily Chen
Mr. Smith is a 62 y/o male. John reports chest pain. Glucose 98 mg/dL.
Rose petals; rose was found. Admitted 05/02/2024.
"""

SENSITIVE_ES = ["JUAN", "PÉREZ", "Pérez", "GONZÁLEZ", "12.345.678-9", "03/04/1970", "0045821",
                "Leones", "8765", "jcperez", "María Gómez", "Juan refiere"]
SENSITIVE_EN = ["Smith", "John", "00482913", "March 14, 1962", "Maple", "555-0143",
                "123-45-6789", "Mary"]


def run(text, **options):
    return anonymize_document(load_text(text), options)


@pytest.mark.parametrize("fmt", ["markdown", "text"])
def test_spanish_patient_data_removed(fmt):
    result = run(ES_TEXT, output_format=fmt)
    for value in SENSITIVE_ES:
        assert value not in result["text"], value
    assert result["language"] == "es"
    assert "[PACIENTE_1]" in result["text"]
    # Información clínica intacta
    assert "Hemoglobina 13.5 g/dL" in result["text"]
    assert "plaquetas 250.000" in result["text"]
    assert "12/05/2024" in result["text"]  # fechas clínicas se conservan por defecto
    assert "54 años" in result["text"]


def test_professionals_are_optional():
    kept = run(ES_TEXT)
    assert "Roberto Soto Muñoz" in kept["text"]
    removed = run(ES_TEXT, anonymize_professionals=True)
    assert "Soto" not in removed["text"]
    assert "[PROFESIONAL_1]" in removed["text"]
    assert "ANAMNESIS" in removed["text"]


def test_english_document():
    result = run(EN_TEXT, anonymize_professionals=True)
    assert result["language"] == "en"
    for value in SENSITIVE_EN + ["Emily", "Chen"]:
        assert value not in result["text"], value
    assert "[PATIENT_1]" in result["text"]
    assert "rose was found" in result["text"]  # palabra común en minúscula no se toca
    assert "Glucose 98 mg/dL" in result["text"]


def test_all_dates_option():
    result = run(ES_TEXT, anonymize_all_dates=True)
    assert "12/05/2024" not in result["text"]
    assert "[FECHA_1]" in result["text"]


def test_tag_style_and_consistency():
    result = run(ES_TEXT, replacement_style="tag", output_format="text")
    assert "[PACIENTE]" in result["text"]
    assert "_1]" not in result["text"]
    patient = next(e for e in run(ES_TEXT)["entities"] if e["category"] == "PATIENT")
    assert patient["count"] >= 3  # nombre rotulado + "Sr. Pérez" + "Juan refiere"


def test_exclusion_and_custom_terms():
    result = run(ES_TEXT, exclude=["María Gómez"], custom_terms=["Providencia", "San José"])
    assert "María Gómez" in result["text"]
    assert "San José" not in result["text"]
    assert "[OCULTO_1]" in result["text"]


def test_language_override_changes_placeholders():
    result = run(ES_TEXT, language="en")
    assert "[PATIENT_1]" in result["text"]


def test_accent_insensitive_propagation():
    text = "Paciente: José Muñoz\nEl paciente JOSE MUNOZ fue dado de alta. Control Sr. Munoz."
    result = run(text, output_format="text")
    assert "JOSE" not in result["text"] and "Munoz" not in result["text"]


def test_lowercase_words_not_redacted():
    text = "Nombre: Rosa Blanco\nPiel blanco rosa, sin lesiones. La Sra. Blanco refiere mejoría."
    result = run(text, output_format="text")
    assert "Piel blanco rosa" in result["text"]
    assert "Sra. Blanco" not in result["text"]


def test_lab_values_untouched():
    text = ("Nombre: Ana Ruiz\nHemograma: Hb 12.1 g/dL; Leucocitos 7.500/mm3; Plaquetas 1.234.567\n"
            "PA 120/80 mmHg. FC 78 lpm. Sat 98%. Glicemia 105 mg/dL a las 10:30.")
    result = run(text, output_format="text")
    for value in ["12.1", "7.500", "120/80", "10:30", "105 mg/dL", "1.234.567"]:
        assert value in result["text"], value


def test_detect_language():
    assert detect_language("El paciente presenta dolor y fiebre de 3 días") == "es"
    assert detect_language("The patient reports pain and fever for 3 days") == "en"


def test_pdf_with_tables(tmp_path: Path):
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import make_samples

    pdf = tmp_path / "es.pdf"
    make_samples.epicrisis_es(pdf)
    result = anonymize_document(load_bytes(pdf.name, pdf.read_bytes()), {"anonymize_professionals": True})
    text = result["text"]
    assert result["pages"] == 2
    for value in ["ROJAS", "Rojas", "María", "15.234.567-K", "21/08/1985", "778201", "Acacias",
                  "7123", "mf.rojas", "Pedro", "Valenzuela", "9.876.543-2"]:
        assert value not in text, value
    assert "| Hemoglobina | 12.8 | g/dL | 12.0 - 16.0 |" in text
    assert text.count("Página") == 2  # sólo los separadores; el pie "Página N" se elimina

    pdf_en = tmp_path / "en.pdf"
    make_samples.lab_report_en(pdf_en)
    result = anonymize_document(load_bytes(pdf_en.name, pdf_en.read_bytes()))
    assert result["language"] == "en"
    for value in ["Johnson", "Robert", "55120934", "07/19/1958", "Oak Street", "555-0199"]:
        assert value not in result["text"], value
    assert "| Glucose | 142 | H | 70-99 mg/dL |" in result["text"]


def test_invalid_file_type():
    from anonymizer import ExtractionError

    with pytest.raises(ExtractionError):
        load_bytes("foto.png", b"\x89PNG....")
