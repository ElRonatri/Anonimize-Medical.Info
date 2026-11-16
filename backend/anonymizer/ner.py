"""Segunda pasada OPCIONAL con NER (spaCy) para nombres de personas y organizaciones.

Las reglas no detectan nombres sin etiqueta ni tratamiento («acude con su hija Bernardita
Quiroga»). Esta pasada los busca con un modelo estadístico y los entrega a la misma propagación
de nombres que usan las reglas (se ocultan en todo el documento).

* Variante de build opcional (`build.bat --ner`): spaCy y sus modelos van DENTRO del ejecutable;
  nunca se descargan. Si no están instalados, `available()` es False y la pasada no existe.
* Modelo: `xx_ent_wiki_sm` (multilingüe, MIT) para español e inglés. Ver docs/ner.md.
* Confianza: probabilidad de cada entidad según *beam search* del propio modelo (0-1). Se usan
  sólo las entidades con confianza >= umbral.
* Falsos positivos: el modelo marca con total seguridad «Diabetes Mellitus» como persona. Se
  descartan entidades con dígitos, sin mayúscula inicial, o formadas por términos clínicos
  (`data/clinical_terms.txt`, editable) y palabras genéricas. En organizaciones se recorta la parte
  genérica («Servicio de Urgencia del Hospital del Salvador» -> «Hospital del Salvador»).
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Preferencia de modelos por idioma (el primero instalado gana).
# xx_ent_wiki_sm (MIT) es el que instala requirements-ner.txt: en la evaluación (scripts/eval_ner.py)
# igualó o superó a es_core_news_sm (GPL-3.0) y a en_core_web_sm. Los otros sólo se usan si alguien
# los instala explícitamente (y asume su licencia).
MODELS = {
    "es": ("xx_ent_wiki_sm", "es_core_news_sm"),
    "en": ("xx_ent_wiki_sm", "en_core_web_sm"),
}
PERSON_LABELS = {"PER", "PERSON"}
ORG_LABELS = {"ORG"}
DEFAULT_THRESHOLD = 0.80
BEAM_WIDTH = 16
CHUNK_CHARS = 20_000  # spaCy procesa bloques acotados (memoria predecible)

# Palabras que inician la parte "propia" de una organización.
ORG_KEYWORDS = {"hospital", "clinica", "clinic", "centro", "center", "cesfam", "consultorio",
                "instituto", "institute", "universidad", "university", "laboratorio", "laboratory",
                "fundacion", "foundation", "sanatorio", "policlinica", "mutual", "isapre"}
_CONNECTORS = {"de", "del", "la", "las", "los", "y", "e", "of", "the", "and", "for", "san", "santa"}
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)

_TITLES = {"sr", "sra", "srta", "dr", "dra", "don", "dona", "mr", "mrs", "ms", "miss", "prof",
           "doctor", "doctora", "senor", "senora", "lic", "enf"}

_lock = threading.Lock()
_pipelines: dict[str, Any] = {}
# Resultados crudos del modelo por documento: cambiar otras opciones no repite el NER.
_raw_cache: dict[str, list[tuple[str, str, float]]] = {}
_RAW_CACHE_SIZE = 32


@dataclass(frozen=True)
class Entity:
    text: str
    label: str  # PERSON | ORG
    score: float


def _norm(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return stripped.lower()


@lru_cache(maxsize=1)
def clinical_terms() -> frozenset[str]:
    path = Path(__file__).resolve().parent / "data" / "clinical_terms.txt"
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        words.update(_norm(w) for w in line.split())
    return frozenset(words)


# --------------------------------------------------------------------------- disponibilidad

def _installed(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


@lru_cache(maxsize=1)
def available_models() -> dict[str, str]:
    """Idioma -> paquete del modelo instalado (vacío si spaCy no está incluido en el build)."""
    if not _installed("spacy"):
        return {}
    found = {}
    for lang, candidates in MODELS.items():
        model = next((m for m in candidates if _installed(m)), None)
        if model:
            found[lang] = model
    return found


def available(lang: str | None = None) -> bool:
    models = available_models()
    return bool(models) if lang is None else lang in models


def info() -> dict:
    return {"available": available(), "models": available_models(), "threshold": DEFAULT_THRESHOLD}


def _model_dir(model: str) -> Path:
    import importlib

    package = Path(importlib.import_module(model).__file__ or "").resolve().parent
    return next(p for p in package.iterdir() if p.is_dir() and (p / "config.cfg").is_file())


def _load_light(model: str, lang: str) -> Any:
    """Sólo los pesos NER de un modelo multilingüe sobre el tokenizador liviano del idioma.

    El tokenizador multilingüe de xx_ent_wiki_sm ocupa ~400 MB de RAM al cargarse; los pesos de
    NER trabajan con hashes de rasgos de cada palabra y no dependen de él. Medido: +30 MB y
    0,16 s (frente a +403 MB y 2 s) con entidades idénticas (docs/ner.md).
    """
    import spacy
    from spacy.util import load_config

    model_dir = _model_dir(model)
    config = load_config(model_dir / "config.cfg", interpolate=True)
    component = dict(config["components"]["ner"])
    component.pop("factory", None)
    nlp = spacy.blank(lang)
    nlp.add_pipe("ner", config=component)
    nlp.get_pipe("ner").from_disk(model_dir / "ner", exclude=["vocab"])
    return nlp


def _pipeline(lang: str) -> Any:
    model = available_models().get(lang)
    if model is None:
        raise RuntimeError(f"ner_model_missing:{lang}")
    key = f"{model}:{lang}"
    with _lock:
        if key not in _pipelines:
            if model.startswith("xx_"):
                _pipelines[key] = _load_light(model, lang)
            else:
                import spacy

                # Sólo lo necesario para NER: más rápido y menos memoria.
                _pipelines[key] = spacy.load(model, exclude=["parser", "lemmatizer", "attribute_ruler",
                                                            "morphologizer", "tagger", "senter"])
        return _pipelines[key]


# --------------------------------------------------------------------------- reconocimiento

def _chunks(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        if size + len(line) > CHUNK_CHARS and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _scored_entities(nlp: Any, text: str) -> list[tuple[str, str, float]]:
    """(texto, etiqueta, probabilidad) de cada entidad según beam search del modelo."""
    doc = nlp.make_doc(text)
    for name, proc in nlp.pipeline:
        if name != "ner":
            doc = proc(doc)
    ner = nlp.get_pipe("ner")
    beams = ner.beam_parse([doc], beam_width=BEAM_WIDTH, beam_density=0.0001)
    scores: dict[tuple[int, int, str], float] = defaultdict(float)
    for beam in beams:
        for score, ents in ner.moves.get_beam_parses(beam):
            for start, end, label in ents:
                scores[(start, end, label)] += score
    out = []
    for (s, e, label), score in scores.items():
        # Una entidad nunca cruza líneas: el modelo a veces une el final de una línea con la
        # etiqueta de la siguiente («Ñuñoa\nTeléfono»).
        for part in doc[s:e].text.split("\n"):
            if part.strip():
                out.append((part.strip(), label, score))
    return out


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def capitalized_runs(text: str) -> list[list[str]]:
    """Tramos de palabras con mayúscula (con conectores internos) dentro de una entidad.

    El modelo a veces devuelve spans largos que mezclan etiquetas y nombres
    («Médico tratante: Dra. Carolina Ibáñez Reyes»); cada tramo se evalúa por separado.
    """
    runs: list[list[str]] = []
    current: list[str] = []
    for word in _words(" ".join(text.split())):
        if word[0].isupper():
            current.append(word)
        elif _norm(word) in _CONNECTORS and current:
            current.append(word)
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)
    cleaned = []
    for run in runs:
        while run and _norm(run[-1]) in _CONNECTORS:
            run = run[:-1]
        if run:
            cleaned.append(run)
    return cleaned


def _as_text(words: list[str]) -> str:
    return " ".join(words)


def person_from_run(run: list[str], stop: frozenset[str] = frozenset()) -> str | None:
    """Nombre de persona plausible a partir de un tramo, o None.

    * Se quitan tratamientos iniciales («Dra. Carolina Ibáñez» -> «Carolina Ibáñez»).
    * Se exigen 2 a 5 palabras con mayúscula: una palabra suelta («Ayer», «Durante») es la
      principal fuente de falsos positivos, y los nombres de pila sueltos ya los cubre la
      propagación cuando el nombre completo aparece en el documento.
    * Se descarta si contiene términos clínicos o palabras genéricas, o si son siglas.
    """
    while run and _norm(run[0]) in _TITLES:
        run = run[1:]
    proper = [w for w in run if _norm(w) not in _CONNECTORS]
    if not 2 <= len(proper) <= 5:
        return None
    lexicon = clinical_terms() | stop
    if any(_norm(w) in lexicon for w in proper):
        return None
    if all(w.isupper() and len(w) <= 4 for w in proper):
        return None  # siglas («HTA DM»)
    return _as_text(run)


def org_from_run(run: list[str], stop: frozenset[str] = frozenset()) -> str | None:
    """Parte identificatoria de una institución dentro de un tramo, o None.

    Desde la palabra de institución («Hospital», «Clínica»...) y con al menos una palabra
    específica: «Servicio de Urgencia del Hospital del Salvador» -> «Hospital del Salvador»;
    «Hospital Regional» (sólo palabras genéricas) -> None.
    """
    norms = [_norm(w) for w in run]
    start = next((i for i, n in enumerate(norms) if n in ORG_KEYWORDS), None)
    if start is None:
        return None
    run, norms = run[start:], norms[start:]
    lexicon = (clinical_terms() | stop) - ORG_KEYWORDS
    specific = [w for w, n in zip(run, norms, strict=False)
                if n not in lexicon and n not in ORG_KEYWORDS and n not in _CONNECTORS]
    return _as_text(run) if specific else None


def clean_person(text: str, stop: frozenset[str] = frozenset()) -> str | None:
    """Primer nombre de persona plausible dentro del texto de una entidad."""
    if any(c.isdigit() for c in text) or len(text) > 120:
        return None
    return next((p for run in capitalized_runs(text) if (p := person_from_run(run, stop))), None)


def clean_org(text: str, stop: frozenset[str] = frozenset()) -> str | None:
    """Primera institución plausible dentro del texto de una entidad."""
    if len(text) > 120:
        return None
    return next((o for run in capitalized_runs(text) if (o := org_from_run(run, stop))), None)


def raw_entities(text: str, lang: str) -> list[tuple[str, str, float]]:
    """Todas las entidades del modelo con su probabilidad (cacheado por documento y modelo)."""
    model = available_models()[lang]
    key = model + ":" + hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()
    with _lock:
        cached = _raw_cache.get(key)
    if cached is not None:
        return cached
    nlp = _pipeline(lang)
    result = [entity for chunk in _chunks(text) for entity in _scored_entities(nlp, chunk)]
    with _lock:
        if len(_raw_cache) >= _RAW_CACHE_SIZE:
            _raw_cache.pop(next(iter(_raw_cache)))
        _raw_cache[key] = result
    return result


def find_entities(text: str, lang: str, threshold: float = DEFAULT_THRESHOLD, orgs: bool = False,
                  stop: frozenset[str] = frozenset()) -> list[Entity]:
    """Personas (y organizaciones) con confianza >= umbral que pasan los filtros."""
    if not available(lang):
        return []
    found: dict[tuple[str, str], float] = {}
    for raw, label, score in raw_entities(text, lang):
        if score < threshold or label not in PERSON_LABELS | ORG_LABELS or any(c.isdigit() for c in raw):
            continue
        for run in capitalized_runs(raw):
            # El modelo confunde etiquetas (marca «Hospital del Salvador» como persona): cada
            # tramo se evalúa como institución y como persona, según corresponda.
            org = org_from_run(run, stop) if orgs else None
            person = None if org or org_from_run(run, stop) else (
                person_from_run(run, stop) if label in PERSON_LABELS else None)
            for kind, cleaned in (("ORG", org), ("PERSON", person)):
                if cleaned:
                    key = (cleaned, kind)
                    found[key] = max(found.get(key, 0.0), score)
    return [Entity(t, k, round(s, 3)) for (t, k), s in sorted(found.items())]
