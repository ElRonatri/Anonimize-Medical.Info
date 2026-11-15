import pytest

from anonymizer import anonymize_document, load_text
from anonymizer.identifiers import anonimizar, resolver_region

# (texto, debe_contener, no_debe_contener)
CASOS = [
    ("Paciente RUN 12.345.678-5 ingresa", "[RUN_CL]", "12.345.678"),
    ("rut 12345678-5", "[RUN_CL]", "12345678"),
    ("RUN inválido 12.345.678-9", None, "[RUN_CL]"),
    ("RUN 123456785 sin guion", "[RUN_CL]", "123456785"),
    ("Pasaporte N° AB1234567 venezolano", "[PASAPORTE]", "AB1234567"),
    ("passport no: X12345678", "[PASAPORTE]", "X12345678"),
    ("Ficha clínica: 458921", "[FICHA_CLINICA]", "458921"),
    ("CUIL 20-12345678-6", "[CUIL_AR]", "12345678"),
    ("DNI 12.345.678 argentino", "[", "12.345.678"),
    ("CPF 529.982.247-25", "[CPF_BR]", "529.982.247"),
    ("CURP GODE561231HDFRRN09", "[CURP_MX]", "GODE561231"),
    ("CI V-12.345.678 venezolano", "[CI_VE]", "12.345.678"),
    ("CI 1.234.567-2 uruguayo", "[CI_UY]", "1.234.567-2"),
    ("SSN 123-45-6789", "[SSN_US]", "6789"),
    ("DNI 12345678Z", "[DNI_ES]", "12345678Z"),
    ("NIE X1234567L", "[NIE_ES]", "X1234567L"),
    ("NIR 1 85 05 78 006 084 91", "[NIR_FR]", "006 084"),
    ("CF RSSMRA85T10A562S", "[CF_IT]", "RSSMRA85T10A562S"),
    ("NHS 943 476 5919", "[NHS_UK]", "5919"),
    ("ID 11010519491231002X", "[ID_CN]", "1231002X"),
    ("Aadhaar 2341 2341 2346", "[AADHAAR_IN]", "2346"),
    ("CC 1020304050 colombiana", "[ID_CC]", "1020304050"),
    ("CIN 001-234-567-8 haitiano", "[ID_CIN]", "567"),
    ("PESEL 44051401359", "[ID_PESEL]", "44051401359"),
    ("Cédula 1710034065 ecuatoriana", "[CI_EC]", "1710034065"),
    ("Hb 12.3 g/dL, sin 2 dosis, pan 100 g", None, "["),
    ("Fecha 12-03-2025, peso 70 kg", None, "["),
    ("P<CHLPEREZ<<JUAN<<<<<<<<<<<<<<<<<<<<<<<<<<<<", "[MRZ]", "PEREZ"),
    ("L898902C36UTO7408122F1204159ZE184226B<<<<<10", "[MRZ]", "L898902C3"),
]


@pytest.mark.parametrize("texto,debe,no_debe", CASOS)
def test_modulo_identificadores(texto, debe, no_debe):
    r = anonimizar(texto)
    assert debe is None or debe in r, r
    assert no_debe is None or no_debe not in r, r


def test_agresivo_respeta_fechas():
    r = anonimizar("Tel 912345678, folio 7788990, fecha 2025-03-12", agresivo=True)
    assert "912345678" not in r and "7788990" not in r
    assert "2025-03-12" in r


def test_resolver_region():
    assert resolver_region("general") is None
    assert resolver_region("all") == frozenset()
    assert "CL" in resolver_region("latam")
    assert resolver_region("br") == frozenset({"BR"})


def run(text, **options):
    return anonymize_document(load_text(text), {"output_format": "text", **options})["text"]


DOC = """Paciente: Ana Souza
CPF 529.982.247-25. Cartão SUS 898 0010 0000 0007.
Pasaporte N° AB1234567. CC 1020304050.
Hb 12.3 g/dL. Plaquetas 250.000. Fecha 12-03-2025.
"""


def test_region_general_no_cambia_comportamiento():
    out = run(DOC)
    assert "529.982.247-25" in out  # sin región, el CPF no tiene etiqueta reconocida
    assert "Ana" not in out


def test_region_pais_especifico():
    out = run(DOC, region="BR")
    assert "[CPF_BR_1]" in out and "529.982.247" not in out
    assert "[PASAPORTE_1]" in out and "AB1234567" not in out
    assert "[ID_CC_1]" in out  # capa contextual activa en cualquier región
    assert "Hb 12.3 g/dL" in out and "250.000" in out and "12-03-2025" in out


def test_region_filtra_patrones_estructurales():
    out = run("Brasileña 529.982.247-25 del paciente", region="CL")
    assert "529.982.247-25" in out  # el CPF brasileño sólo se busca si Brasil está activo
    out = run("Brasileña 529.982.247-25 del paciente", region="latam")
    assert "[CPF_BR_1]" in out


def test_region_chile_valida_digito():
    out = run("Ingresa con RUN 12.345.678-5 y control.", region="CL")
    assert "[RUN_CL_1]" in out
    # Con etiqueta reconocida se oculta igual aunque el dígito sea inválido (más seguro).
    out = run("RUT: 12.345.678-9", region="CL")
    assert "12.345.678-9" not in out


def test_marcadores_localizados_en_ingles():
    out = run("Passport no: X12345678. The patient denies pain.", region="all", language="en")
    assert "[PASSPORT_1]" in out


def test_numeros_agresivos():
    out = run(DOC, aggressive_numbers=True)
    assert "[NUMERO_" in out
    assert "12-03-2025" in out and "250.000" in out
