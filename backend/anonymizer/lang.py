"""Recursos dependientes del idioma: etiquetas de marcadores y detección de idioma."""

from __future__ import annotations

import re

SUPPORTED_LANGUAGES = ("es", "en")

# Texto de los marcadores de reemplazo por categoría e idioma.
PLACEHOLDERS: dict[str, dict[str, str]] = {
    "es": {
        "PATIENT": "PACIENTE",
        "PERSON": "PERSONA",
        "PROFESSIONAL": "PROFESIONAL",
        "ID": "ID",
        "RECORD": "N_FICHA",
        "BIRTHDATE": "FECHA_NACIMIENTO",
        "DATE": "FECHA",
        "PHONE": "TELEFONO",
        "EMAIL": "EMAIL",
        "ADDRESS": "DIRECCION",
        "URL": "URL",
        "IP": "IP",
        "CUSTOM": "OCULTO",
    },
    "en": {
        "PATIENT": "PATIENT",
        "PERSON": "PERSON",
        "PROFESSIONAL": "PROVIDER",
        "ID": "ID",
        "RECORD": "RECORD_NO",
        "BIRTHDATE": "BIRTH_DATE",
        "DATE": "DATE",
        "PHONE": "PHONE",
        "EMAIL": "EMAIL",
        "ADDRESS": "ADDRESS",
        "URL": "URL",
        "IP": "IP",
        "CUSTOM": "REDACTED",
    },
}

PAGE_LABEL = {"es": "Página", "en": "Page"}
NO_TEXT_PAGE = {
    "es": "[Página sin texto extraíble: posible documento escaneado]",
    "en": "[Page without extractable text: possibly a scanned document]",
}

_STOPWORDS = {
    "es": {
        "el", "la", "los", "las", "de", "del", "que", "y", "en", "con", "por",
        "para", "una", "uno", "se", "su", "sus", "al", "es", "no", "sin",
        "paciente", "fecha", "años", "dolor", "presenta", "refiere", "examen",
        "diagnóstico", "tratamiento", "control", "historia", "clínica",
    },
    "en": {
        "the", "and", "of", "to", "in", "with", "for", "is", "was", "on", "at",
        "by", "no", "patient", "date", "years", "pain", "history", "exam",
        "diagnosis", "treatment", "follow", "denies", "reports", "presents",
    },
}

_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def detect_language(text: str, default: str = "es") -> str:
    """Detecta (de forma heurística) si un texto está en español o en inglés."""
    counts = {lang: 0 for lang in SUPPORTED_LANGUAGES}
    for word in _WORD_RE.findall(text[:50000].lower()):
        for lang, words in _STOPWORDS.items():
            if word in words:
                counts[lang] += 1
    if counts["es"] == counts["en"]:
        return default
    return max(counts, key=lambda lang: counts[lang])
