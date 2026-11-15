"""Genera PDFs de ejemplo con datos FICTICIOS para probar la aplicación.

Uso:  python scripts/make_samples.py [carpeta_destino]
Requiere: pip install reportlab
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _header(title: str, patient_line: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2 * cm, doc.pagesize[1] - 1.2 * cm, title)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, doc.pagesize[1] - 1.6 * cm, patient_line)
        canvas.drawRightString(doc.pagesize[0] - 2 * cm, 1 * cm, f"Página {doc.page}")
        canvas.restoreState()
    return draw


def _table(rows):
    table = Table(rows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    return table


def epicrisis_es(path: Path) -> None:
    styles = getSampleStyleSheet()
    p = lambda t, s="BodyText": Paragraph(t, styles[s])  # noqa: E731
    story = [
        p("EPICRISIS", "Title"),
        p("<b>Nombre:</b> MARÍA FERNANDA ROJAS SILVA &nbsp;&nbsp;&nbsp;&nbsp; <b>RUT:</b> 15.234.567-K"),
        p("<b>Fecha de nacimiento:</b> 21/08/1985 &nbsp;&nbsp;&nbsp;&nbsp; <b>Edad:</b> 39 años"),
        p("<b>Ficha clínica:</b> 778201 &nbsp;&nbsp;&nbsp;&nbsp; <b>Previsión:</b> FONASA B"),
        p("<b>Dirección:</b> Pasaje Las Acacias 455, Maipú"),
        p("<b>Teléfono:</b> +56 9 7123 4567 &nbsp;&nbsp;&nbsp;&nbsp; <b>Correo:</b> mf.rojas@correo.cl"),
        p("<b>Acompañante:</b> Pedro Rojas Díaz"),
        Spacer(1, 10),
        p("DIAGNÓSTICO DE EGRESO", "Heading2"),
        p("1. Colecistitis aguda litiásica."),
        p("2. Hipertensión arterial crónica."),
        p("EVOLUCIÓN", "Heading2"),
        p("Paciente de 39 años ingresa el 02/03/2025 por dolor abdominal en hipocondrio derecho. "
          "La Sra. Rojas evoluciona favorablemente tras colecistectomía laparoscópica realizada "
          "por el Dr. Andrés Valenzuela. María tolera régimen liviano al segundo día."),
        PageBreak(),
        p("EXÁMENES DE LABORATORIO", "Heading2"),
        _table([
            ["Examen", "Resultado", "Unidad", "Rango referencia"],
            ["Hemoglobina", "12.8", "g/dL", "12.0 - 16.0"],
            ["Leucocitos", "11.200", "/mm3", "4.500 - 11.000"],
            ["PCR", "48", "mg/L", "< 5"],
            ["Bilirrubina total", "1.4", "mg/dL", "0.3 - 1.2"],
        ]),
        Spacer(1, 10),
        p("INDICACIONES AL ALTA", "Heading2"),
        p("• Paracetamol 1 g cada 8 horas por 5 días."),
        p("• Control con cirujano en 10 días (Dr. Valenzuela)."),
        Spacer(1, 20),
        p("<b>Médico tratante:</b> Dr. Andrés Valenzuela Ortiz &nbsp;&nbsp; <b>RUT:</b> 9.876.543-2"),
    ]
    header = _header("HOSPITAL REGIONAL DEL SUR - Servicio de Cirugía",
                     "Paciente: MARÍA FERNANDA ROJAS SILVA  -  Ficha: 778201")
    SimpleDocTemplate(str(path), pagesize=A4, topMargin=2.5 * cm).build(
        story, onFirstPage=header, onLaterPages=header)


def lab_report_en(path: Path) -> None:
    styles = getSampleStyleSheet()
    p = lambda t, s="BodyText": Paragraph(t, styles[s])  # noqa: E731
    story = [
        p("LABORATORY REPORT", "Title"),
        _table([
            ["Patient Name:", "Johnson, Robert L.", "MRN:", "55120934"],
            ["DOB:", "07/19/1958", "Sex:", "M"],
            ["Ordering Physician:", "Dr. Sarah Patel", "Collected:", "11/02/2025"],
        ]),
        Spacer(1, 10),
        p("Address: 88 Oak Street, Portland, OR 97205 &nbsp;&nbsp;&nbsp; Phone: (503) 555-0199"),
        Spacer(1, 10),
        _table([
            ["Test", "Result", "Flag", "Reference"],
            ["Glucose", "142", "H", "70-99 mg/dL"],
            ["HbA1c", "7.4", "H", "< 5.7 %"],
            ["Creatinine", "1.1", "", "0.7-1.3 mg/dL"],
        ]),
        Spacer(1, 10),
        p("Comment: Mr. Johnson should follow up with his PCP regarding glycemic control."),
        p("Electronically signed by: Sarah Patel, MD"),
    ]
    SimpleDocTemplate(str(path), pagesize=LETTER).build(story)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples")
    out.mkdir(parents=True, exist_ok=True)
    epicrisis_es(out / "epicrisis_ejemplo.pdf")
    lab_report_en(out / "lab_report_example.pdf")
    print(f"PDFs de ejemplo creados en: {out.resolve()}")


if __name__ == "__main__":
    main()
