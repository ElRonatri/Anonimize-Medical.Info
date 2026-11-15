"""
Identificadores personales por país (documentos nacionales, pasaporte, seguridad
social, salud, ficha clínica) para textos clínicos.

Tres capas:
  1. ESTRUCTURALES: formatos con estructura propia (letras, separadores o
     longitud) + validación de dígito verificador cuando existe. No requieren
     contexto. Ej.: RUN 12.345.678-5, CURP, CPF 123.456.789-09, NIR francés.
     Se filtran según el país / región elegidos en la interfaz.
  2. CONTEXTUALES: palabra clave + valor. Cubre los identificadores que son
     solo dígitos y que sin contexto se confunden con cualquier número
     (DNI peruano, CC colombiana, PESEL, BSN, pasaporte, ficha clínica, etc.).
  3. AGRESIVA (opcional): enmascara cualquier secuencia de >= 7 dígitos.

Uso independiente:
    from anonymizer.identifiers import anonimizar
    anonimizar("Paciente RUN 12.345.678-5, pasaporte AB123456")
    -> "Paciente RUN [RUN_CL], pasaporte [PASAPORTE]"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

# Límites de token: no pegado a letras/dígitos.
B = r"(?<![A-Za-z0-9])"
E = r"(?![A-Za-z0-9])"


_NO_DIGITOS = re.compile(r"\D")
_NO_ALNUM_MAYUS = re.compile(r"[^A-Z0-9]+")


def _digits(s: str) -> str:
    return _NO_DIGITOS.sub("", s)


# ----------------------------------------------------------------------------
# Validadores de dígito verificador
# ----------------------------------------------------------------------------
def v_run_cl(s: str) -> bool:
    s = s.replace(".", "").replace("-", "").upper()
    cuerpo, dv = s[:-1], s[-1]
    suma, m = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * m
        m = m + 1 if m < 7 else 2
    r = 11 - suma % 11
    esperado = "0" if r == 11 else "K" if r == 10 else str(r)
    return dv == esperado


def v_cuit_ar(s: str) -> bool:
    d = _digits(s)
    if len(d) != 11:
        return False
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    r = 11 - sum(int(a) * b for a, b in zip(d, pesos)) % 11
    r = 0 if r == 11 else r
    return r != 10 and r == int(d[10])


def v_cpf_br(s: str) -> bool:
    d = _digits(s)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        r = sum(int(d[i]) * (n + 1 - i) for i in range(n)) * 10 % 11
        if r % 10 != int(d[n]):
            return False
    return True


def v_cns_br(s: str) -> bool:
    d = _digits(s)
    return len(d) == 15 and d[0] in "12789" and \
        sum(int(x) * (15 - i) for i, x in enumerate(d)) % 11 == 0


def v_ci_ec(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10:
        return False
    prov, tercero = int(d[:2]), int(d[2])
    if not (1 <= prov <= 24 or prov == 30) or tercero >= 6:
        return False
    suma = 0
    for i in range(9):
        p = int(d[i]) * (2 if i % 2 == 0 else 1)
        suma += p - 9 if p > 9 else p
    return (10 - suma % 10) % 10 == int(d[9])


def v_ci_uy(s: str) -> bool:
    d = _digits(s)
    if not 7 <= len(d) <= 8:
        return False
    cuerpo, dv = d[:-1].zfill(7), int(d[-1])
    suma = sum(int(a) * b for a, b in zip(cuerpo, [2, 9, 8, 7, 6, 3, 4]))
    return (10 - suma % 10) % 10 == dv


_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def v_dni_es(s: str) -> bool:
    s = s.replace("-", "").replace(" ", "").upper()
    return _LETRAS_DNI[int(s[:8]) % 23] == s[8]


def v_nie_es(s: str) -> bool:
    s = s.replace("-", "").replace(" ", "").upper()
    num = str("XYZ".index(s[0])) + s[1:8]
    return _LETRAS_DNI[int(num) % 23] == s[8]


def v_nir_fr(s: str) -> bool:
    s = s.replace(" ", "").upper()
    if len(s) != 15:
        return False
    cuerpo = s[:13].replace("2A", "19").replace("2B", "18")
    if not cuerpo.isdigit():
        return False
    return 97 - int(cuerpo) % 97 == int(s[13:])


def v_id_cn(s: str) -> bool:
    s = s.upper()
    pesos = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    suma = sum(int(a) * b for a, b in zip(s[:17], pesos))
    return "10X98765432"[suma % 11] == s[17]


_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
       [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
       [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
       [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def v_aadhaar_in(s: str) -> bool:
    d = _digits(s)
    c = 0
    for i, x in enumerate(reversed(d)):
        c = _VD[c][_VP[i % 8][int(x)]]
    return len(d) == 12 and c == 0


def v_nhs_uk(s: str) -> bool:
    d = _digits(s)
    if len(d) != 10:
        return False
    r = 11 - sum(int(d[i]) * (10 - i) for i in range(9)) % 11
    r = 0 if r == 11 else r
    return r != 10 and r == int(d[9])


def v_luhn(s: str) -> bool:
    d = _digits(s)
    suma = 0
    for i, x in enumerate(reversed(d)):
        n = int(x)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        suma += n
    return suma % 10 == 0


def v_hetu_fi(s: str) -> bool:
    s = s.upper()
    n = int(s[:6] + s[7:10])
    return "0123456789ABCDEFHJKLMNPRSTUVWXY"[n % 31] == s[10]


def v_mrz_cd(campo: str, dv: str) -> bool:
    """Dígito verificador ICAO 9303 (pesos 7-3-1)."""
    def val(c):
        if c.isdigit():
            return int(c)
        if c == "<":
            return 0
        return ord(c) - 55
    pesos = [7, 3, 1]
    return sum(val(c) * pesos[i % 3] for i, c in enumerate(campo)) % 10 == int(dv)


def v_mrz_td3_l2(s: str) -> bool:
    # Valida N° de documento, fecha de nacimiento y vencimiento.
    return (v_mrz_cd(s[0:9], s[9]) and v_mrz_cd(s[13:19], s[19])
            and v_mrz_cd(s[21:27], s[27]))


# ----------------------------------------------------------------------------
# Capa 1: patrones estructurales
# ----------------------------------------------------------------------------
@dataclass
class Patron:
    etiqueta: str          # se usa como reemplazo: [ETIQUETA]
    pais: str
    nombre: str
    regex: str
    validador: Optional[Callable[[str], bool]] = None
    flags: int = 0


_ESTADOS_MX = ("AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|OC|PL|"
               "QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE")

ESTRUCTURALES: list[Patron] = [
    # --- Pasaporte / documentos de viaje (ICAO 9303) ---
    Patron("MRZ", "Internacional", "MRZ pasaporte TD3 línea 1",
           B + r"P[A-Z<][A-Z<]{3}[A-Z<]{39}" + E),
    Patron("MRZ", "Internacional", "MRZ pasaporte TD3 línea 2",
           B + r"[A-Z0-9<]{9}\d[A-Z<]{3}\d{6}\d[MFX<]\d{6}\d[A-Z0-9<]{14}[0-9<]\d" + E,
           v_mrz_td3_l2),
    Patron("MRZ", "Internacional", "MRZ cédula TD1 línea 1",
           B + r"[AIC][A-Z<][A-Z<]{3}[A-Z0-9<]{9}\d[A-Z0-9<]{15}" + E),

    # --- América ---
    Patron("RUN_CL", "Chile", "RUN/RUT",
           B + r"\d{1,2}(?:\.\d{3}\.\d{3}|\d{6})-[\dkK]" + E, v_run_cl),
    Patron("CUIL_AR", "Argentina", "CUIL/CUIT",
           B + r"(?:20|23|24|27|30|33|34)-\d{8}-\d" + E, v_cuit_ar),
    Patron("DNI_AR", "Argentina", "DNI con puntos",
           B + r"\d{1,2}\.\d{3}\.\d{3}" + r"(?![-\dA-Za-z])"),
    Patron("CPF_BR", "Brasil", "CPF",
           B + r"\d{3}\.\d{3}\.\d{3}-\d{2}" + E, v_cpf_br),
    Patron("CNS_BR", "Brasil", "Cartão Nacional de Saúde",
           B + r"[12789]\d{2}\s?\d{4}\s?\d{4}\s?\d{4}" + E, v_cns_br),
    Patron("CURP_MX", "México", "CURP",
           B + r"[A-Z][AEIOUX][A-Z]{2}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
           r"[HMX](?:" + _ESTADOS_MX + r")[B-DF-HJ-NP-TV-Z]{3}[A-Z\d]\d" + E),
    Patron("RFC_MX", "México", "RFC",
           B + r"[A-ZÑ&]{3,4}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[A-Z\d]{2}[A\d]" + E),
    Patron("CI_VE", "Venezuela", "Cédula de Identidad (V-/E-)",
           B + r"[VE]-?\d{1,2}\.?\d{3}\.?\d{3}" + E),
    Patron("RIF_VE", "Venezuela", "RIF",
           B + r"[VEJPG]-\d{8}-\d" + E),
    Patron("CI_UY", "Uruguay", "Cédula de Identidad",
           B + r"\d\.\d{3}\.\d{3}-\d" + E, v_ci_uy),
    Patron("CI_EC", "Ecuador", "Cédula de Identidad",
           B + r"\d{9}-?\d" + E, v_ci_ec),
    Patron("SSN_US", "EE.UU.", "Social Security Number",
           B + r"(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}" + E),
    Patron("MBI_US", "EE.UU.", "Medicare Beneficiary Identifier",
           B + r"[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y\d]\d-?[AC-HJKMNP-RT-Y]"
           r"[AC-HJKMNP-RT-Y\d]\d-?[AC-HJKMNP-RT-Y]{2}\d{2}" + E),
    Patron("SIN_CA", "Canadá", "Social Insurance Number",
           B + r"[1-79]\d{2}[- ]\d{3}[- ]\d{3}" + E, v_luhn),

    # --- Europa ---
    Patron("DNI_ES", "España", "DNI/NIF",
           B + r"\d{8}-?[A-HJ-NP-TV-Z]" + E, v_dni_es, re.I),
    Patron("NIE_ES", "España", "NIE",
           B + r"[XYZ]-?\d{7}-?[A-HJ-NP-TV-Z]" + E, v_nie_es, re.I),
    Patron("NIR_FR", "Francia", "NIR (Sécurité sociale)",
           B + r"[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?(?:\d{2}|2[AB])\s?\d{3}\s?\d{3}\s?\d{2}" + E,
           v_nir_fr),
    Patron("CF_IT", "Italia", "Codice Fiscale",
           B + r"[A-Z]{6}[\dLMNP-V]{2}[A-EHLMPR-T][\dLMNP-V]{2}[A-Z][\dLMNP-V]{3}[A-Z]" + E,
           None, re.I),
    Patron("NINO_UK", "Reino Unido", "National Insurance Number",
           B + r"(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]" + E),
    Patron("NHS_UK", "Reino Unido", "NHS Number",
           B + r"\d{3}[ -]\d{3}[ -]\d{4}" + E, v_nhs_uk),
    Patron("PNR_SE_DK", "Suecia/Dinamarca/Noruega", "Personnummer / CPR",
           B + r"(?:19|20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]\d{4}" + E
           + r"|" + B + r"(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}-\d{4}" + E),
    Patron("HETU_FI", "Finlandia", "Henkilötunnus",
           B + r"(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}[-+A-FU-Y]\d{3}[0-9A-FHJ-NPR-Y]" + E,
           v_hetu_fi),
    Patron("AHV_CH", "Suiza/Liechtenstein", "AHV/AVS",
           B + r"756\.?\d{4}\.?\d{4}\.?\d{2}" + E),

    # --- Asia ---
    Patron("ID_CN", "China", "Resident Identity Card",
           B + r"[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]" + E,
           v_id_cn),
    Patron("AADHAAR_IN", "India", "Aadhaar",
           B + r"[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}" + E, v_aadhaar_in),
    Patron("PAN_IN", "India", "PAN",
           B + r"[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]" + E),
    Patron("RRN_KR", "Corea del Sur", "Resident Registration Number",
           B + r"\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])-[1-8]\d{6}" + E),
    Patron("NRIC_SG", "Singapur", "NRIC/FIN",
           B + r"[STFGM]\d{7}[A-Z]" + E),
    Patron("HKID_HK", "Hong Kong", "HKID",
           B + r"[A-Z]{1,2}\d{6}\([0-9A]\)"),
    Patron("CNIC_PK", "Pakistán", "CNIC",
           B + r"\d{5}-\d{7}-\d" + E),
    Patron("EID_AE", "Emiratos Árabes Unidos", "Emirates ID",
           B + r"784-?\d{4}-?\d{7}-?\d" + E, v_luhn),
]

# País del patrón -> códigos ISO 3166-1 alfa-2 ("*" = se aplica en cualquier región).
PAIS_CODIGOS: dict[str, tuple[str, ...]] = {
    "Internacional": ("*",),
    "Chile": ("CL",), "Argentina": ("AR",), "Brasil": ("BR",), "México": ("MX",),
    "Venezuela": ("VE",), "Uruguay": ("UY",), "Ecuador": ("EC",),
    "EE.UU.": ("US",), "Canadá": ("CA",),
    "España": ("ES",), "Francia": ("FR",), "Italia": ("IT",), "Reino Unido": ("GB",),
    "Suecia/Dinamarca/Noruega": ("SE", "DK", "NO"), "Finlandia": ("FI",),
    "Suiza/Liechtenstein": ("CH", "LI"),
    "China": ("CN",), "India": ("IN",), "Corea del Sur": ("KR",), "Singapur": ("SG",),
    "Hong Kong": ("HK",), "Pakistán": ("PK",), "Emiratos Árabes Unidos": ("AE",),
}

# Regiones seleccionables en la interfaz. Los países sin patrón estructural propio
# (p. ej. Colombia, Perú, Alemania) usan la capa contextual (palabra clave + valor).
REGIONES: dict[str, tuple[str, ...]] = {
    "latam": ("AR", "BO", "BR", "CL", "CO", "CR", "EC", "MX", "PE", "PY", "UY", "VE"),
    "north_america": ("US", "CA"),
    "europe": ("ES", "PT", "FR", "IT", "DE", "NL", "GB", "IE", "SE", "DK", "NO", "FI",
               "CH", "LI", "PL"),
    "asia": ("CN", "IN", "KR", "JP", "SG", "HK", "PK", "AE"),
}

GENERAL = "general"  # sin capa por país (comportamiento base de la aplicación)
ALL = "all"


def resolver_region(region: str | None) -> Optional[frozenset[str]]:
    """Devuelve los códigos de país activos, frozenset() vacío = todos, None = desactivado."""
    if not region or region == GENERAL:
        return None
    region = region.strip()
    if region == ALL:
        return frozenset()
    if region in REGIONES:
        return frozenset(REGIONES[region])
    return frozenset({region.upper()})


def formatos_por_pais() -> dict[str, list[str]]:
    """Código de país -> nombres de los formatos estructurales validados (para la interfaz)."""
    out: dict[str, list[str]] = {}
    for p in ESTRUCTURALES:
        for code in PAIS_CODIGOS.get(p.pais, ()):
            if code != "*" and p.nombre not in out.setdefault(code, []):
                out[code].append(p.nombre)
    return out


def patrones_para(paises: Optional[frozenset[str]]) -> list[tuple[Patron, re.Pattern]]:
    if paises is None:
        return []
    if not paises:  # todas
        return _COMPILADOS
    return [(p, rx) for p, rx in _COMPILADOS
            if "*" in PAIS_CODIGOS.get(p.pais, ()) or paises & set(PAIS_CODIGOS.get(p.pais, ()))]


# ----------------------------------------------------------------------------
# Capa 2: palabra clave + valor
# ----------------------------------------------------------------------------
# Insensibles a mayúsculas. Orden: más largas primero (lo hace el código).
KW_CI = [
    # Pasaporte / generales
    r"pasaporte", r"passport(?:\s+n(?:o|umber))?", r"passeport", r"passaporte", r"reisepass",
    r"document(?:o)?\s+(?:n[uú]mero|number|de\s+identidad|nacional\s+de\s+identidad|de\s+viaje)",
    r"n[°º]\s*(?:de\s+)?documento", r"licencia(?:\s+de\s+conducir)?",
    r"driver'?s?\s+licen[cs]e", r"permiso\s+de\s+residencia", r"identity\s+card", r"id\s+card",
    r"national\s+id(?:entity)?(?:\s+(?:card|number))?", r"personal\s+(?:id\s+)?number",
    r"c[eé]dula(?:\s+de\s+(?:identidad(?:\s+(?:personal|civil|y\s+electoral))?|ciudadan[ií]a|extranjer[ií]a))?",
    r"carn[eé]t?(?:\s+de\s+(?:identidad|extranjer[ií]a))?", r"carte\s+(?:nationale\s+)?d['’]identit[eé]",
    r"bilhete\s+de\s+identidade", r"identificaci[oó]n", r"credencial(?:\s+para\s+votar)?",
    # Ficha clínica / salud / seguridad social
    r"ficha(?:\s+cl[ií]nica)?", r"n[°º]\s*(?:de\s+)?ficha", r"historia\s+cl[ií]nica",
    r"medical\s+record(?:\s+number)?", r"mrn", r"nhc", r"prontu[aá]rio",
    r"n[°º]\s*(?:de\s+)?afiliad[oa]", r"afiliad[oa]", r"seguridad\s+social", r"seguro\s+social",
    r"social\s+security(?:\s+number)?", r"social\s+insurance(?:\s+number)?",
    r"health\s+card(?:\s+number)?", r"n[uú]mero\s+de\s+utente", r"tarjeta\s+sanitaria",
    r"tessera\s+sanitaria", r"carte\s+vitale", r"s[eé]curit[eé]\s+sociale",
    r"cart[aã]o\s+(?:nacional\s+de\s+)?sa[uú]de", r"cart[aã]o\s+de\s+cidad[aã]o",
    r"national\s+insurance(?:\s+number)?", r"nhs(?:\s+number)?", r"medicare(?:\s+number)?",
    r"medicaid(?:\s+id)?", r"fonasa", r"isapre", r"imss", r"philhealth", r"bpjs(?:\s+kesehatan)?",
    # Chile y Latinoamérica
    r"rol\s+[uú]nico\s+(?:nacional|tributario)", r"run", r"rut", r"dni", r"cuil", r"cuit",
    r"nuip", r"dimex", r"dui", r"dpi", r"curp", r"rfc", r"nss", r"rif", r"cpf", r"ohip",
    r"ramq",
    # Europa
    r"steuer-?id", r"kvnr", r"svnr", r"niss", r"insz", r"rijksregisternummer",
    r"registre\s+national", r"egn", r"oib", r"cpr(?:-nummer)?", r"rodn[eé]\s+[cč][ií]slo",
    r"em[sš]o", r"nie", r"nif", r"nuss", r"naf", r"isikukood", r"henkil[oö]tunnus", r"hetu",
    r"amka", r"afm", r"taj(?:\s+sz[aá]m)?", r"ppsn?", r"kennitala", r"codice\s+fiscale",
    r"personas\s+kods", r"asmens\s+kodas", r"matricule(?:\s+national)?", r"bsn",
    r"burgerservicenummer", r"pesel", r"nhs", r"chi\s+number", r"nino", r"cnp",
    r"personnummer", r"samordningsnummer", r"f[oø]dselsnummer", r"d-nummer", r"ahv(?:-nr)?",
    r"avs", r"cass", r"jmbg", r"embg", r"idnp", r"rnokpp", r"unzr", r"snils",
    r"t\.?\s?c\.?\s+kimlik(?:\s+no)?", r"kimlik(?:\s+no)?",
    # Asia / Medio Oriente
    r"hkid", r"my\s*number", r"hokensho", r"aadhaar", r"abha", r"cnic", r"nicop", r"tazkira",
    r"code\s+melli", r"teudat\s+zehut", r"iqama", r"emirates\s+id", r"qid", r"civil\s+id",
    r"mykad", r"nric", r"philsys", r"pinfl", r"cccd", r"c[aă]n\s+c[uư][oớ]c",
    # África / Oceanía
    r"omang", r"fayda", r"nida", r"maisha\s+namba", r"nhis", r"ghana\s+card", r"bvn",
    r"indangamuntu", r"nuit", r"ird(?:\s+number)?", r"tfn", r"nhi(?:\s+number)?", r"fnpf",
]
# Sensibles a mayúsculas: siglas que también son palabras o sílabas comunes
# ("sin", "pan", "ce", "cc", "bi", "ins"...). Solo se detectan en MAYÚSCULAS.
KW_CS = [
    r"CI", r"CC", r"TI", r"RC", r"CE", r"PPT", r"NIT", r"CUI", r"RG", r"CNS", r"TRN", r"NIB",
    r"SSN", r"ITIN", r"SIN", r"MBI", r"PHN", r"IHI", r"MBO", r"CIP", r"TSI", r"NIR", r"INS",
    r"CIE", r"CF", r"LBO", r"IPN", r"INN", r"OMS", r"FIN", r"IIN", r"BIR", r"RRN", r"PAN",
    r"EPIC", r"PSN", r"SSS", r"TIN", r"NRC", r"NIK", r"KTP", r"SHA", r"BI", r"DIP", r"NID",
    r"NIN", r"NIC", r"CIN", r"CNI", r"CNIE", r"CNIB", r"NNI", r"NPI", r"NINA", r"NIP", r"SNS",
    r"HC", r"PPN", r"ID", r"NI", r"MR", r"DOC",
]

_SEP = r"(?i:\s*(?:n[°ºo]\.?|nro\.?|n[uú]m(?:ero)?\.?|number|#|:|=|-)\s*)*\s*"
# Valor: alfanumérico; une partes con . - / y con espacio solo si sigue un dígito.
_VALOR = r"[A-Za-z0-9](?:[A-Za-z0-9]|[./-](?=[A-Za-z0-9])|[ \t](?=\d)){3,24}"

_kw_ci = "|".join(sorted(KW_CI, key=len, reverse=True))
_kw_cs = "|".join(sorted(KW_CS, key=len, reverse=True))
# Se aplica sobre el texto completo: los espacios nunca cruzan saltos de línea.
CONTEXTUAL = re.compile((
    B + r"(?P<kw>(?i:" + _kw_ci + r")|(?:" + _kw_cs + r"))\.?" + E + _SEP
    + r"(?P<valor>" + _VALOR + r")" + r"(?![A-Za-z0-9])"
).replace(r"\s", r"[ \t]"))


def _contextual(kw: str, primera: str) -> re.Pattern:
    # La anticipación del primer carácter permite descartar rápido las posiciones imposibles.
    return re.compile((
        f"(?={primera})" + B + r"(?P<kw>" + kw + r")\.?" + E + _SEP
        + r"(?P<valor>" + _VALOR + r")" + r"(?![A-Za-z0-9])"
    ).replace(r"\s", r"[ \t]"))


# Palabras clave insensibles a mayúsculas: se buscan en minúsculas sobre el texto en minúsculas
# (sin IGNORECASE, ≈2x más rápido). Las siglas sensibles, sobre el texto original.
CONTEXTUAL_CI = _contextual(_kw_ci, "[a-z]")
CONTEXTUAL_CS = _contextual(_kw_cs, "[A-Z]")
_MINUSCULAS = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
_MINUSCULAS.update({c: c + 32 for c in range(0xC0, 0xDF) if c != 0xD7})

_ETIQUETA_KW = [
    (r"pas|ppn|reisepass|mrz", "PASAPORTE"),
    (r"ficha|mrn|nhc|historia|medical\s+record|prontu|^hc$|^mr$", "FICHA_CLINICA"),
    (r"^ru[nt]$|rol\s+[uú]nico", "RUN_CL"),
]


_ETIQUETA_KW_RE = [(re.compile(patron), etiqueta) for patron, etiqueta in _ETIQUETA_KW]


def _etiqueta_contextual(kw: str) -> str:
    k = kw.strip().lower()
    for patron, etiqueta in _ETIQUETA_KW_RE:
        if patron.search(k):
            return etiqueta
    return "ID_" + _NO_ALNUM_MAYUS.sub("_", kw.strip().upper()).strip("_")[:20]


# ----------------------------------------------------------------------------
# Capa 3: agresiva
# ----------------------------------------------------------------------------
# Secuencias de >= 7 dígitos (permitiendo . - espacio entre grupos). Excluye
# fechas (dd-mm-aaaa / aaaa-mm-dd) para no destruir la cronología clínica.
AGRESIVO = re.compile(B + r"\d(?:\d|[.\- ](?=\d)){6,}\d?" + E)
_FECHA = re.compile(r"^(?:\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})$")


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
@dataclass
class Hallazgo:
    inicio: int
    fin: int
    texto: str
    etiqueta: str
    capa: str  # "estructural" | "contextual" | "agresiva"


def _primer_caracter(cuerpo: str) -> Optional[str]:
    """Clase del primer carácter de un patrón (para una anticipación rápida), o None."""
    while cuerpo.startswith("(?!"):  # saltar anticipaciones negativas iniciales
        nivel, i = 0, 0
        for i, c in enumerate(cuerpo):
            if c == "(" and (i == 0 or cuerpo[i - 1] != "\\"):
                nivel += 1
            elif c == ")" and cuerpo[i - 1] != "\\":
                nivel -= 1
                if nivel == 0:
                    break
        cuerpo = cuerpo[i + 1:]
    if cuerpo.startswith(r"\d"):
        return r"\d"
    if cuerpo.startswith("["):
        fin = cuerpo.find("]", 1)
        return cuerpo[:fin + 1] if fin > 0 else None
    if cuerpo[:1].isalnum():
        return re.escape(cuerpo[0])
    return None


def _compilar(p: Patron) -> re.Pattern:
    """Precompila el patrón anteponiendo una anticipación del primer carácter.

    Las expresiones empiezan con un lookbehind, lo que impide al motor descartar
    rápido las posiciones imposibles; la anticipación (?=[...]) lo vuelve ~3x más rápido.
    """
    regex = p.regex
    if regex.startswith(B) and "|" + B not in regex:
        primero = _primer_caracter(regex[len(B):])
        if primero:
            regex = f"(?={primero})" + regex
    return re.compile(regex, p.flags)


_COMPILADOS = [(p, _compilar(p)) for p in ESTRUCTURALES]


def estructurales(texto: str, paises: Optional[frozenset[str]] = frozenset(),
                  validar: bool = True) -> list[Hallazgo]:
    hallazgos = []
    for p, rx in patrones_para(paises):
        for m in rx.finditer(texto):
            if validar and p.validador:
                try:
                    if not p.validador(m.group(0)):
                        continue
                except (ValueError, IndexError):
                    continue
            hallazgos.append(Hallazgo(m.start(), m.end(), m.group(0), p.etiqueta, "estructural"))
    return hallazgos


def contextuales(texto: str) -> list[Hallazgo]:
    hallazgos = []
    minusculas = texto.lower()
    if len(minusculas) != len(texto):  # algunos caracteres Unicode cambian de longitud
        minusculas = texto.translate(_MINUSCULAS)
    coincidencias = [(m, texto) for m in CONTEXTUAL_CI.finditer(minusculas)]
    coincidencias += [(m, texto) for m in CONTEXTUAL_CS.finditer(texto)]
    for m, _ in coincidencias:
        valor = texto[m.start("valor"):m.end("valor")].rstrip(".-/ ")
        if sum(c.isdigit() for c in valor) < 4 or _FECHA.match(valor):
            continue
        ini = m.start("valor")
        kw = texto[m.start("kw"):m.end("kw")]
        hallazgos.append(Hallazgo(ini, ini + len(valor), valor, _etiqueta_contextual(kw), "contextual"))
    return hallazgos


def agresivos(texto: str) -> list[Hallazgo]:
    return [Hallazgo(m.start(), m.end(), m.group(0), "NUMERO", "agresiva")
            for m in AGRESIVO.finditer(texto)
            if not _FECHA.match(m.group(0)) and len(_digits(m.group(0))) >= 7]


def encontrar(texto: str, agresivo: bool = False, validar: bool = True,
              paises: Optional[frozenset[str]] = frozenset()) -> list[Hallazgo]:
    """Devuelve los identificadores encontrados, sin solapamientos."""
    hallazgos = estructurales(texto, paises, validar) + contextuales(texto)
    if agresivo:
        hallazgos += agresivos(texto)

    # Resolver solapamientos: prioridad estructural > contextual > agresiva, luego el más largo.
    prioridad = {"estructural": 0, "contextual": 1, "agresiva": 2}
    hallazgos.sort(key=lambda h: (prioridad[h.capa], -(h.fin - h.inicio), h.inicio))
    elegidos: list[Hallazgo] = []
    for h in hallazgos:
        if all(h.fin <= e.inicio or h.inicio >= e.fin for e in elegidos):
            elegidos.append(h)
    return sorted(elegidos, key=lambda h: h.inicio)


def anonimizar(texto: str, agresivo: bool = False, formato: str = "[{etiqueta}]") -> str:
    """Reemplaza cada identificador por formato.format(etiqueta=...)."""
    out, pos = [], 0
    for h in encontrar(texto, agresivo=agresivo):
        out.append(texto[pos:h.inicio])
        out.append(formato.format(etiqueta=h.etiqueta))
        pos = h.fin
    out.append(texto[pos:])
    return "".join(out)
