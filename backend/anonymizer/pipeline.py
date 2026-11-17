"""Punto de entrada de alto nivel: documento -> texto anonimizado + reporte."""

from __future__ import annotations

import time
from typing import Any

from .detector import Options, Redactor, build_knowledge
from .document import Document
from .lang import SUPPORTED_LANGUAGES, detect_language
from .render import render, strip_repeated_lines


def anonymize_document(doc: Document, options: dict[str, Any] | Options | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    opts = options if isinstance(options, Options) else Options.from_dict(options)

    full_text = doc.full_text()
    detected = detect_language(full_text)
    lang = opts.language if opts.language in SUPPORTED_LANGUAGES else detected

    # La detección usa SIEMPRE el texto completo (los encabezados suelen traer el nombre).
    knowledge = build_knowledge(full_text, opts, lang)
    redactor = Redactor(knowledge, opts, lang)

    view = strip_repeated_lines(doc) if opts.remove_repeated else doc
    output = render(view, redactor.redact, opts.output_format, lang, opts.page_markers)

    entities = redactor.entities()
    return {
        "text": output,
        "format": "text" if opts.output_format == "text" else "markdown",
        "language": lang,
        "detected_language": detected,
        "pages": len(doc.pages),
        "ocr_pages": sum(1 for p in doc.pages if p.ocr),
        "ocr_engine": doc.ocr_engine,
        "empty_pages": sum(1 for p in doc.pages if p.empty),
        "entities": entities,
        "replacements": sum(e["count"] for e in entities),
        "warnings": list(doc.warnings),
        "ner": knowledge.ner_summary,
        "characters": len(full_text),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
