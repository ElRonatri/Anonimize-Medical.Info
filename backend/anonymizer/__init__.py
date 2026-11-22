"""Motor de anonimización de documentos médicos (español / inglés)."""

from .detector import Options
from .extract import ExtractionError, load_bytes, load_document, load_text
from .pipeline import anonymize_document

__version__ = "1.2.0"

__all__ = [
    "Options",
    "ExtractionError",
    "anonymize_document",
    "load_bytes",
    "load_document",
    "load_text",
    "__version__",
]
