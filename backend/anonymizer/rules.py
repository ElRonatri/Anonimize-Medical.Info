"""Reglas de detección: etiquetas (ES/EN) y patrones de identificadores personales."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

# --------------------------------------------------------------------------- utilidades

UPPER = "A-ZÁÉÍÓÚÑÜÀÈÌÒÙÂÊÎÔÛÄËÏÖÇ"
LOWER = "a-záéíóúñüàèìòùâêîôûäëïöç"
LETTER = UPPER + LOWER

PARTICLES = {"de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos", "di",
             "van", "von", "der", "den", "mc", "mac", "san", "st"}

TITLES = {"dr", "dra", "dres", "drs", "sr", "sra", "srta", "sres", "don", "doña", "dña",
          "mr", "mrs", "ms", "miss", "mx", "prof", "lic", "enf", "eu", "klgo", "klga",
          "tm", "ing", "mg", "ps", "nut", "doctor", "doctora", "señor", "señora"}

# Palabras con mayúscula que NO forman parte de un nombre propio.
NON_NAME_WORDS = {
    "edad", "sexo", "género", "genero", "masculino", "femenino", "hombre", "mujer",
    "varón", "varon", "rut", "run", "dni", "nie", "ci", "cc", "fecha", "hora", "años",
    "año", "meses", "días", "historia", "ficha", "clínica", "clinica", "diagnóstico",
    "diagnostico", "servicio", "cama", "sala", "previsión", "prevision", "fonasa",
    "isapre", "teléfono", "telefono", "dirección", "direccion", "domicilio", "n", "nº",
    "n°", "no", "nro", "número", "numero", "paciente", "nombre", "nombres", "apellido",
    "apellidos", "médico", "medico", "tratante", "firma", "timbre", "edad:", "peso",
    "talla", "estado", "civil", "soltero", "soltera", "casado", "casada", "viudo",
    "viuda", "divorciado", "divorciada", "ocupación", "nacionalidad", "chilena",
    "chileno", "examen", "exámenes", "resultado", "resultados", "informe", "epicrisis",
    "ingreso", "egreso", "alta", "unidad", "hospital", "clínico", "desconocido",
    "ninguno", "ninguna", "anónimo", "anonimo", "n/a", "na", "s/i", "si", "sí",
    # inglés
    "age", "sex", "gender", "male", "female", "man", "woman", "date", "time", "dob",
    "mrn", "id", "ssn", "record", "number", "chart", "patient", "name", "physician",
    "provider", "unit", "room", "bed", "service", "diagnosis", "report", "results",
    "result", "single", "married", "widowed", "divorced", "unknown", "none", "years",
    "old", "yo", "y/o", "admission", "discharge", "phone", "address", "insurance",
    "page", "página", "pagina", "of", "de", "the", "and",
}

NAME_TOKEN_RE = re.compile(rf"^[{UPPER}][{LETTER}'’\-]*$")
INITIAL_RE = re.compile(rf"^[{UPPER}]\.$")


@dataclass(frozen=True)
class LabelRule:
    category: str  # categoría del valor (PATIENT, PERSON, PROFESSIONAL, ID, ...)
    kind: str  # name | id | date | phone | address | text
    labels: tuple[str, ...]  # expresiones regulares (sin anclar) de la etiqueta
    colon_required: bool = True


# --------------------------------------------------------------------------- etiquetas

PATIENT_LABELS = (
    r"nombre\s+del\s+paciente", r"nombre\s+de\s+la\s+paciente", r"nombre\s+paciente",
    r"nombre\s+completo", r"nombres?\s+y\s+apellidos?", r"apellidos?\s+y\s+nombres?",
    r"nombre\s*\(s\)", r"nombres?", r"apellidos?", r"primer\s+apellido",
    r"segundo\s+apellido", r"apellido\s+paterno", r"apellido\s+materno", r"paciente",
    r"pcte\.?", r"pac\.", r"usuario\s*\(a\)", r"usuari[oa]", r"beneficiari[oa]",
    r"afiliad[oa]", r"titular", r"sr\s*\(a\)\.?", r"paciente\s+de\s+nombre",
    # inglés
    r"patient\s+name", r"patient's\s+name", r"pt\.?\s+name", r"full\s+name",
    r"first\s+name", r"given\s+name", r"middle\s+name", r"last\s+name", r"surname",
    r"family\s+name", r"name", r"patient", r"member\s+name", r"insured\s+name",
    r"beneficiary",
)

PROFESSIONAL_LABELS = (
    r"nombre\s+del\s+m[ée]dico", r"m[ée]dico\s+tratante", r"m[ée]dico\s+solicitante",
    r"m[ée]dico\s+responsable", r"m[ée]dico\s+de\s+turno", r"m[ée]dico\s+residente",
    r"m[ée]dico\s+informante", r"m[ée]dico", r"profesional(?:\s+responsable)?",
    r"tratante", r"doctora?", r"firmado\s+por", r"firma\s+m[ée]dico", r"solicitado\s+por",
    r"solicitante", r"informado\s+por", r"validado\s+por", r"revisado\s+por",
    r"realizado\s+por", r"atendido\s+por", r"enfermer[oa](?:\s+responsable)?",
    r"matr[oó]na", r"kinesi[oó]log[oa]", r"tecn[oó]log[oa]\s+m[ée]dic[oa]",
    r"residente", r"cirujan[oa]", r"anestesi[oó]log[oa]", r"anestesista",
    r"ayudante", r"especialista", r"interconsultor",
    # inglés
    r"attending(?:\s+physician)?", r"physician", r"provider", r"referring\s+(?:physician|provider|doctor)",
    r"ordering\s+(?:physician|provider)", r"primary\s+care\s+(?:physician|provider)", r"pcp",
    r"(?:electronically\s+)?signed\s+by", r"reviewed\s+by", r"verified\s+by",
    r"reported\s+by", r"dictated\s+by", r"performed\s+by", r"nurse", r"surgeon",
    r"anesthesiologist", r"consultant",
)

PERSON_LABELS = (
    r"madre", r"padre", r"tutor(?:a)?(?:\s+legal)?", r"apoderad[oa]", r"acompañante",
    r"familiar(?:\s+responsable)?", r"contacto(?:\s+de\s+emergencia)?",
    r"en\s+caso\s+de\s+emergencia(?:\s+avisar\s+a)?", r"c[oó]nyuge", r"espos[oa]",
    r"hij[oa]", r"herman[oa]", r"pareja", r"cuidador(?:a)?", r"informante",
    r"representante\s+legal",
    # inglés
    r"mother", r"father", r"parent", r"guardian", r"next\s+of\s+kin",
    r"emergency\s+contact(?:\s+name)?", r"contact\s+person", r"spouse", r"caregiver",
    r"informant", r"legal\s+representative",
)

RECORD_LABELS = (
    r"n[°ºo]?\.?\s*(?:de\s+)?(?:historia|ficha)\s+cl[ií]nica", r"historia\s+cl[ií]nica",
    r"ficha(?:\s+cl[ií]nica)?", r"n\.?\s*h\.?\s*c\.?", r"h\.\s*c\.", r"hc",
    r"expediente(?:\s+cl[ií]nico)?", r"n[°ºo]?\.?\s*(?:de\s+)?expediente",
    r"episodio", r"n[°ºo]?\.?\s*(?:de\s+)?episodio", r"n[°ºo]?\.?\s*(?:de\s+)?admisi[oó]n",
    r"admisi[oó]n", r"n[°ºo]?\.?\s*(?:de\s+)?cuenta", r"n[°ºo]?\.?\s*(?:de\s+)?ingreso",
    r"n[°ºo]?\.?\s*(?:de\s+)?orden", r"n[°ºo]?\.?\s*(?:de\s+)?muestra", r"folio",
    r"id\s+(?:del\s+)?paciente", r"c[oó]digo\s+(?:del\s+)?paciente", r"registro",
    # inglés
    r"mrn", r"m\.r\.n\.", r"mr\s*#", r"medical\s+record(?:\s+(?:number|no\.?|#))?",
    r"chart(?:\s+(?:number|no\.?|#))?", r"account(?:\s+(?:number|no\.?|#))?",
    r"encounter(?:\s+(?:id|number|no\.?|#))?", r"visit(?:\s+(?:id|number|no\.?|#))?",
    r"accession(?:\s+(?:number|no\.?|#))?", r"case(?:\s+(?:number|no\.?|#))",
    r"patient\s+id", r"specimen\s+(?:id|number|no\.?)", r"order\s+(?:number|no\.?|#)",
)

ID_LABELS_STRONG = (
    r"r\.?u\.?t\.?", r"r\.u\.n\.?", r"d\.?n\.?i\.?", r"n\.?i\.?e\.?", r"n\.?i\.?f\.?",
    r"c[ée]dula(?:\s+de\s+(?:identidad|ciudadan[ií]a))?", r"cuil", r"cuit", r"curp",
    r"rfc", r"nss", r"n[°ºo]?\.?\s*(?:de\s+)?seguridad\s+social", r"pasaporte",
    r"documento(?:\s+de\s+identidad)?", r"identificaci[oó]n", r"tarjeta\s+sanitaria",
    r"n[°ºo]?\.?\s*(?:de\s+)?afiliad[oa]", r"n[°ºo]?\.?\s*(?:de\s+)?p[oó]liza", r"p[oó]liza",
    # inglés
    r"ssn", r"social\s+security(?:\s+(?:number|no\.?|#))?", r"passport(?:\s+(?:number|no\.?))?",
    r"driver'?s\s+licen[cs]e(?:\s+(?:number|no\.?))?", r"insurance\s+(?:id|number|no\.?|#)",
    r"member\s+(?:id|number|no\.?|#)", r"subscriber\s+id", r"policy\s+(?:number|no\.?|#)",
    r"medicare(?:\s+(?:id|number|no\.?))?", r"medicaid(?:\s+(?:id|number|no\.?))?",
    r"nhs\s+(?:number|no\.?)", r"health\s+card(?:\s+(?:number|no\.?))?",
)

ID_LABELS_WEAK = (r"run", r"c\.?\s?i\.?", r"c\.?\s?c\.?", r"id", r"doc\.?", r"dni\s*/\s*nie")

BIRTH_LABELS = (
    r"fecha\s+de\s+nacimiento", r"f(?:ec(?:ha)?)?\.?\s*(?:de\s+)?nac(?:imiento|\.)?",
    r"nacimiento", r"f\.\s*n\.", r"nacid[oa]\s+el", r"date\s+of\s+birth", r"birth\s*date",
    r"d\.?o\.?b\.?", r"born(?:\s+on)?",
)

PHONE_LABELS = (
    r"tel[ée]fonos?(?:\s+(?:de\s+)?contacto)?", r"tel[ée]f\.?", r"tel\.?", r"tfno\.?",
    r"fonos?", r"celular", r"cel\.?", r"m[oó]vil", r"whatsapp", r"fax",
    r"(?:home|work|cell|mobile|contact)\s+phone", r"phone(?:\s+(?:number|no\.?|#))?",
    r"telephone", r"cell", r"mobile", r"contact\s+number",
)

ADDRESS_LABELS = (
    r"direcci[oó]n(?:\s+particular)?", r"domicilio", r"residencia", r"dir\.", r"calle",
    r"comuna", r"localidad", r"barrio", r"colonia", r"vereda", r"municipio",
    r"c[oó]digo\s+postal", r"c\.?\s?p\.", r"ciudad",
    # inglés
    r"(?:home\s+|street\s+|mailing\s+)?address", r"street", r"city", r"zip(?:\s+code)?",
    r"postal\s+code", r"town",
)

EMAIL_LABELS = (r"e-?mail", r"correo(?:\s+electr[oó]nico)?", r"email\s+address")

# Etiquetas que sólo sirven para cortar el valor de otra etiqueta en la misma línea.
STOP_LABELS = (
    r"edad", r"sexo", r"g[ée]nero", r"fecha", r"hora", r"servicio", r"cama", r"sala",
    r"previsi[oó]n", r"isapre", r"seguro", r"diagn[oó]stico", r"peso", r"talla",
    r"procedencia", r"estado\s+civil", r"ocupaci[oó]n", r"religi[oó]n",
    r"nacionalidad", r"especialidad", r"unidad", r"motivo", r"grupo\s+sangu[ií]neo",
    r"age", r"sex", r"gender", r"date", r"time", r"service", r"bed", r"room", r"ward",
    r"diagnosis", r"weight", r"height", r"marital\s+status", r"occupation", r"race",
    r"ethnicity", r"language", r"religion", r"unit", r"department", r"specialty",
    r"blood\s+type", r"insurance", r"payer",
)

LABEL_RULES: tuple[LabelRule, ...] = (
    LabelRule("BIRTHDATE", "date", BIRTH_LABELS, colon_required=False),
    LabelRule("RECORD", "id", RECORD_LABELS, colon_required=False),
    LabelRule("ID", "id", ID_LABELS_STRONG, colon_required=False),
    LabelRule("ID", "id", ID_LABELS_WEAK, colon_required=True),
    LabelRule("PHONE", "phone", PHONE_LABELS, colon_required=False),
    LabelRule("EMAIL", "email", EMAIL_LABELS, colon_required=True),
    LabelRule("ADDRESS", "address", ADDRESS_LABELS, colon_required=True),
    LabelRule("PROFESSIONAL", "name", PROFESSIONAL_LABELS, colon_required=True),
    LabelRule("PERSON", "name", PERSON_LABELS, colon_required=True),
    LabelRule("PATIENT", "name", PATIENT_LABELS, colon_required=True),
)

_NUMBER_MARK = r"(?:\s*(?:n[°º]|no\.|nro\.?|núm\.?|num\.?|#))?"
_SEP_REQUIRED = _NUMBER_MARK + r"\s*(?:[:：](?:\s*\|)?|\|)\s*"
_SEP_OPTIONAL = _NUMBER_MARK + r"\s*(?:[:：#](?:\s*\|)?|\||-\s|\s)\s*"


def _alternation(labels: Iterable[str]) -> str:
    return "|".join(sorted(labels, key=len, reverse=True))


def compile_rule(rule: LabelRule) -> re.Pattern[str]:
    sep = _SEP_REQUIRED if rule.colon_required else _SEP_OPTIONAL
    pattern = rf"(?<![\w]){'(?:' + _alternation(rule.labels) + ')'}(?![\w]){sep}"
    # Las reglas se aplican sobre el texto completo YA EN MINÚSCULAS (ver `lower_same_length`),
    # sin IGNORECASE (≈2x más rápido), y el espacio nunca cruza saltos de línea.
    return re.compile(_single_line(pattern))


# Minúsculas sin cambiar la longitud del texto (str.lower() puede alterarla en Unicode),
# para que las posiciones encontradas sirvan sobre el texto original.
_LOWER_TABLE = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
_LOWER_TABLE.update({c: c + 32 for c in range(0xC0, 0xDF) if c != 0xD7})


def lower_same_length(text: str) -> str:
    lowered = text.lower()  # rápido (C); sólo si conserva la longitud
    return lowered if len(lowered) == len(text) else text.translate(_LOWER_TABLE)


def _single_line(pattern: str) -> str:
    return pattern.replace(r"\s", r"[ \t]")


COMPILED_RULES = [(rule, compile_rule(rule)) for rule in LABEL_RULES]


@lru_cache(maxsize=8)
def combined_rules(professionals: bool, addresses: bool) -> tuple[re.Pattern[str], tuple[LabelRule, ...]]:
    """Todas las reglas activas en UNA expresión precompilada (una sola pasada por el texto).

    Cada regla es un grupo con nombre (r0, r1, ...) y `match.lastgroup` indica cuál coincidió.
    El orden de LABEL_RULES define la prioridad si dos reglas empiezan en la misma posición.
    """
    active = tuple(r for r in LABEL_RULES
                   if (professionals or r.category != "PROFESSIONAL")
                   and (addresses or r.category != "ADDRESS"))
    branches = []
    for i, rule in enumerate(active):
        sep = _SEP_REQUIRED if rule.colon_required else _SEP_OPTIONAL
        branches.append(rf"(?P<r{i}>(?:{_alternation(rule.labels)})(?![\w]){sep})")
    # (?=[a-z...]) descarta de inmediato las posiciones que no empiezan con letra.
    pattern = rf"(?=[a-zà-þ])(?<![\w])(?:{'|'.join(branches)})"
    return re.compile(_single_line(pattern)), active

_ALL_LABELS = (PATIENT_LABELS + PROFESSIONAL_LABELS + PERSON_LABELS + RECORD_LABELS
               + ID_LABELS_STRONG + ID_LABELS_WEAK + BIRTH_LABELS + PHONE_LABELS
               + ADDRESS_LABELS + EMAIL_LABELS + STOP_LABELS)

# Corta el valor al comenzar otra etiqueta "Etiqueta:" en la misma línea.
NEXT_LABEL_RE = re.compile(
    rf"(?<![\w])(?:{_alternation(_ALL_LABELS)})(?![\w]){_NUMBER_MARK}\s*[:：]", re.IGNORECASE)
VALUE_STOP_RE = re.compile(r"\s{3,}|\t|\||;|\s+-\s+")

# --------------------------------------------------------------------------- patrones

# Prefiltros baratos: si una línea no los cumple, se omiten los patrones costosos.
# Algo con forma de identificador: 6+ dígitos (con separadores simples), letras+dígitos
# (CURP, Codice Fiscale, PAN), dígito-letra-dígito (MBI) o "<" (zona MRZ de pasaportes).
ID_CANDIDATE_RE = re.compile(r"\d(?:[.\- /]?\d){5}|[A-Za-z]{3}\d{2}|\d[A-Za-z][A-Za-z0-9]\d|<")
IP_HINT_RE = re.compile(r"\d\.\d{1,3}\.\d")

MONTHS_ES = r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
MONTHS_EN = r"january|february|march|april|may|june|july|august|september|october|november|december"
MONTHS_ABBR = r"ene|feb|mar|abr|may|jun|jul|ago|sep|sept|set|oct|nov|dic|jan|apr|aug|dec"

DATE_PATTERNS = [
    re.compile(r"(?<![\d/.\-])\d{1,2}[/.\-]\d{1,2}[/.\-](?:\d{4}|\d{2})(?![\d/\-]|\.\d)"),
    re.compile(r"(?<![\d/.\-])\d{4}[/\-]\d{1,2}[/\-]\d{1,2}(?![\d/\-])"),
    re.compile(rf"\b\d{{1,2}}\s+de\s+(?:{MONTHS_ES})(?:\s+(?:de|del)\s+\d{{4}})?\b", re.IGNORECASE),
    re.compile(rf"\b(?:{MONTHS_ES})\s+(?:de|del)\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(rf"\b(?:{MONTHS_EN}|{MONTHS_ABBR})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.IGNORECASE),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?[\s\-/](?:{MONTHS_EN}|{MONTHS_ES}|{MONTHS_ABBR})\.?"
               rf"[\s\-/,]+\d{{2,4}}\b", re.IGNORECASE),
]

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\]\)\|]+", re.IGNORECASE)
# (?!\d|\.\d): una IP al final de una oración ("ref 10.0.12.7.") también se detecta.
IP_RE = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d|\.\d)")

ID_PATTERNS = [
    # RUT / RUN chileno: 12.345.678-9 ó 12345678-K
    re.compile(r"(?<![\w.])\d{1,2}\.\d{3}\.\d{3}\s?[-‐‑]\s?[\dkK](?![\w])"),
    re.compile(r"(?<![\w.\-])\d{7,8}[-‐‑][\dkK](?![\w\-])"),
    # SSN (EE.UU.)
    re.compile(r"(?<![\w-])\d{3}-\d{2}-\d{4}(?![\w-])"),
    # DNI / NIE (España)
    re.compile(r"(?<![\w])\d{8}-?[A-HJ-NP-TV-Z](?![\w])"),
    re.compile(r"(?<![\w])[XYZ]-?\d{7}-?[A-Z](?![\w])"),
    # CURP (México)
    re.compile(r"(?<![\w])[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z\d]\d(?![\w])"),
]

PHONE_PATTERNS = [
    re.compile(r"(?<![\w+])\+\d{1,3}[\s.\-]?(?:\(?\d{1,4}\)?[\s.\-]?){2,5}\d{2,4}(?![\w])"),
    re.compile(r"(?<![\w])\(\d{3}\)\s?\d{3}[\-.\s]\d{4}(?![\w])"),
    re.compile(r"(?<![\w.\-])\d{3}[\-.]\d{3}[\-.]\d{4}(?![\w.\-])"),
]

_STREET_ES = (r"calle|c/|avenida|av\.|avda\.?|pasaje|psje\.?|pje\.|carrera|cra\.?|"
              r"jir[oó]n|jr\.|diagonal|camino|paseo|transversal|villa|poblaci[oó]n")
ADDRESS_PATTERNS = [
    re.compile(rf"(?<![\w])(?:{_STREET_ES})\s+[{LETTER}0-9][{LETTER}0-9.'’\- ]{{1,45}}?\s*"
               rf"(?:n[°º]\.?\s*|#\s*|no\.?\s*)?\d{{1,5}}(?:\s*[-,]?\s*(?:depto\.?|dpto\.?|apto\.?|of\.?|casa)\s*\w+)?(?![\w])",
               re.IGNORECASE),
    re.compile(rf"(?<![\w])\d{{1,5}}\s+(?:[{UPPER}][{LOWER}]+\s+){{1,3}}"
               rf"(?:Street|St\.|Avenue|Ave\.?|Road|Rd\.|Boulevard|Blvd\.?|Lane|Ln\.|Drive|Court|Ct\.|Way|Place|Pl\.)"
               rf"(?:,?\s+(?:Apt|Suite|Unit)\.?\s*#?\w+)?"),
]

_NAME_PIECE = rf"[{UPPER}][{LETTER}'’\-]+"
_PARTICLE = r"(?:de|del|la|las|los|van|von|da|di)"
_NAME_SEQ = rf"{_NAME_PIECE}(?:[ \t]+(?:{_PARTICLE}[ \t]+)?(?:{_NAME_PIECE}|[{UPPER}]\.)){{0,4}}"

PROFESSIONAL_PATTERNS = [
    re.compile(rf"(?<![\w])(?:Dr|Dra|Dres|Prof|Lic|Enf|Klgo|Klga|E\.U|T\.M|Mg|Ps|Nut)\.[ \t]*(?P<name>{_NAME_SEQ})"),
    re.compile(rf"(?<![\w])(?:Doctora?|Dr|Dra)[ \t]+(?P<name>{_NAME_SEQ})"),
    re.compile(rf"(?P<name>{_NAME_SEQ}),?[ \t]+(?:MD|M\.D\.|DO|D\.O\.|RN|NP|PA-C|PhD|DDS|FACP|FACS)(?![\w])"),
]

PERSON_PATTERNS = [
    re.compile(rf"(?<![\w])(?:Sr|Sra|Srta|Sres|Mr|Mrs|Ms|Mx)\.?[ \t]+(?P<name>{_NAME_SEQ})"),
    re.compile(rf"(?<![\w])(?:Don|Doña|Miss|Señora?)[ \t]+(?P<name>{_NAME_SEQ})"),
    re.compile(rf"(?<![\w])(?:[Pp]aciente\s+de\s+nombre|[Pp]atient\s+named|[Ss]e\s+llama|[Ll]lamad[oa])"
               rf"[ \t]+(?P<name>{_NAME_SEQ})"),
]
