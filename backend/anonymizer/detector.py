"""Detección de datos personales y reemplazo por marcadores."""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from . import fastmatch, identifiers, rules
from .lang import PLACEHOLDERS

NAME_CATEGORIES = ("PATIENT", "PERSON", "PROFESSIONAL")
CATEGORY_PRIORITY = {c: i for i, c in enumerate(
    ("PATIENT", "BIRTHDATE", "ID", "RECORD", "PERSON", "PHONE", "EMAIL", "ADDRESS",
     "PROFESSIONAL", "CUSTOM", "URL", "IP", "DATE"))}

DIGIT_KINDS = {"ID", "RECORD", "PHONE"}

# Motor para buscar los valores ya detectados (nombres, apellidos, términos personalizados e
# identificadores) en cada línea:
#   "aho"   Aho-Corasick: una pasada, el costo no crece con la cantidad de valores.
#   "regex" una expresión con alternativas: más rápida con pocos valores (sin preparación).
#   "auto"  (por defecto) Aho-Corasick a partir de AHO_MIN_TERMS valores de un mismo tipo.
_ENGINES = ("auto", "aho", "regex")
_literal_engine = "auto" if fastmatch.AVAILABLE else "regex"
AHO_MIN_TERMS = 100  # punto de cruce medido con scripts/bench.py (ver docs/benchmarks.md)


def set_literal_engine(engine: str) -> None:
    global _literal_engine
    if engine not in _ENGINES:
        raise ValueError(f"motor desconocido: {engine}")
    if engine != "regex" and not fastmatch.AVAILABLE:
        raise RuntimeError("pyahocorasick no está instalado")
    _literal_engine = engine


def literal_engine() -> str:
    return _literal_engine


# --------------------------------------------------------------------------- normalización

_NON_ALNUM_RE = re.compile(r"[^0-9a-z]")
_SEP_CLASS_RE = re.compile(r"[/.\-]")


@lru_cache(maxsize=65536)
def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


@lru_cache(maxsize=65536)
def norm(text: str) -> str:
    return " ".join(strip_accents(text).lower().split())


@lru_cache(maxsize=65536)
def norm_digits(text: str) -> str:
    return _NON_ALNUM_RE.sub("", strip_accents(text).lower())


def lookup_key(text: str) -> str:
    """Forma canónica para identificar a qué literal corresponde una coincidencia."""
    return _SEP_CLASS_RE.sub("/", norm(text.replace(",", " ")))


_EQUIV = {"a": "aáàäâ", "e": "eéèëê", "i": "iíìïî", "o": "oóòöô", "u": "uúùüû",
          "n": "nñ", "c": "cç"}


def fuzzy_text_pattern(value: str, space: str = r"\s+") -> str:
    """Regex que ignora tildes, mayúsculas y diferencias de espacios."""
    out = []
    for ch in norm(value):
        if ch == " ":
            out.append(space)
        elif ch in _EQUIV:
            out.append(f"[{_EQUIV[ch]}]")
        elif ch in "/.-":
            out.append(r"[/.\-]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def fuzzy_digits_pattern(value: str) -> str:
    """Regex para identificadores: tolera puntos, guiones y espacios entre caracteres."""
    chars = norm_digits(value)
    return r"[\s.\-/()]?".join(re.escape(c) for c in chars)


def compile_terms(terms) -> re.Pattern | None:
    """Una sola regex precompilada (insensible a tildes/mayúsculas) para una lista de términos."""
    terms = sorted({t for t in terms if t and t.strip()}, key=len, reverse=True)
    if not terms:
        return None
    alternatives = "|".join(fuzzy_text_pattern(t) for t in terms)
    return re.compile(rf"(?<![\w])(?:{alternatives})(?![\w])", re.IGNORECASE)


# --------------------------------------------------------------------------- opciones

@dataclass
class Options:
    language: str = "auto"  # auto | es | en
    output_format: str = "markdown"  # markdown | text
    replacement_style: str = "numbered"  # numbered | tag
    anonymize_professionals: bool = False
    anonymize_all_dates: bool = False
    anonymize_addresses: bool = True
    remove_repeated: bool = True
    page_markers: bool = True
    region: str = "general"  # general | all | latam | europe | ... | código ISO de país
    aggressive_numbers: bool = False  # ocultar cualquier secuencia de >= 7 dígitos
    custom_terms: list[str] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)  # términos que nunca se anonimizan
    exclude: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> Options:
        data = data or {}
        opts = cls()
        for key, value in data.items():
            if hasattr(opts, key) and value is not None:
                setattr(opts, key, value)
        opts.custom_terms = [t.strip() for t in (opts.custom_terms or []) if t and t.strip()]
        opts.whitelist = [t.strip() for t in (opts.whitelist or []) if t and t.strip()]
        opts.exclude = [t for t in (opts.exclude or []) if t]
        return opts


# --------------------------------------------------------------------------- conocimiento

@dataclass
class Literal:
    category: str
    key: str
    value: str
    source: str  # fragmento regex (sin límites) que reconoce el valor
    digits: bool = False  # identificador numérico: se compara sin separadores
    name_token: bool = False  # exige mayúscula inicial en la coincidencia
    label: str | None = None  # marcador específico (p. ej. RUN_CL, PASAPORTE)

    @property
    def lookup(self) -> str:
        return norm_digits(self.value) if self.digits else lookup_key(self.value)


class Knowledge:
    """Valores concretos detectados en el documento (nombres, IDs, fechas...).

    Todos los literales se combinan en DOS expresiones regulares precompiladas (texto y
    dígitos), de modo que cada línea se recorre una sola vez sin importar cuántos
    valores se hayan detectado.
    """

    def __init__(self, excluded: set[str], whitelist: list[str] | None = None):
        self.excluded = excluded
        self.whitelist = {norm(t) for t in (whitelist or [])}
        self.whitelist_re = compile_terms(whitelist or [])
        self.literals: dict[tuple[str, bool], Literal] = {}
        self.token_keys: dict[str, tuple[str, str]] = {}  # token normalizado -> (cat, key)
        self.name_keys: dict[str, tuple[str, set[str]]] = {}  # key -> (cat, tokens)
        self._counter = 0
        self.text_re: re.Pattern | None = None
        self.digit_re: re.Pattern | None = None
        self.text_lookup: dict[str, list[Literal]] = {}
        self.digit_lookup: dict[str, list[Literal]] = {}
        self.term_matcher: fastmatch.TermMatcher | None = None
        self.digit_matcher: fastmatch.TermMatcher | None = None

    def is_excluded(self, value: str) -> bool:
        n = norm(value)
        return n in self.excluded or n in self.whitelist or norm_digits(value) in self.excluded

    # ---------------------------------------------------------------- compilación
    def compile(self) -> Knowledge:
        """Prepara la búsqueda de todos los literales.

        * Nombres, apellidos y términos personalizados -> Aho-Corasick (si está disponible).
        * Resto de textos (direcciones, fechas, correos) -> una regex combinada.
        * Identificadores numéricos -> otra regex combinada (tolera separadores).
        """
        def use_aho(count: int) -> bool:
            return _literal_engine == "aho" or (_literal_engine == "auto" and count >= AHO_MIN_TERMS)

        literals = list(self.literals.values())
        names = [lit for lit in literals if lit.name_token or lit.category == "CUSTOM"]
        digit_lits = [lit for lit in literals if lit.digits]
        self.term_matcher = fastmatch.TermMatcher() if use_aho(len(names)) else None
        self.digit_matcher = fastmatch.TermMatcher(digits=True) if use_aho(len(digit_lits)) else None
        groups: dict[bool, list[Literal]] = {False: [], True: []}
        self.text_lookup, self.digit_lookup = {}, {}
        for lit in literals:
            if self.term_matcher is not None and (lit.name_token or lit.category == "CUSTOM"):
                self.term_matcher.add(lit.value, lit)
                continue
            if self.digit_matcher is not None and lit.digits:
                self.digit_matcher.add(lit.value, lit)
                continue
            groups[lit.digits].append(lit)
            table = self.digit_lookup if lit.digits else self.text_lookup
            table.setdefault(lit.lookup, []).append(lit)

        def build(lits: list[Literal]) -> re.Pattern | None:
            if not lits:
                return None
            ordered = sorted(lits, key=lambda item: len(item.value), reverse=True)
            # Fin de cada valor: si termina en dígito sólo se exige que no siga OTRO dígito. El OCR
            # suele pegar el campo siguiente ("21/08/1985Edad:", "778201Previsión:"); con el
            # límite de palabra estricto esos datos quedaban visibles. Los nombres mantienen
            # el límite estricto ("Rosa" no debe ocultarse dentro de "Rosalía").
            alternatives = [f"(?:{lit.source}){_end_boundary(lit.value)}" for lit in ordered]
            alternatives = list(dict.fromkeys(alternatives))  # sin duplicados, O(n)
            return re.compile(rf"(?<![\w])(?:{'|'.join(alternatives)})", re.IGNORECASE)

        self.text_re = build(groups[False])
        self.digit_re = build(groups[True])
        for matcher in (self.term_matcher, self.digit_matcher):
            if matcher is not None:
                matcher.build()
        return self

    def _store(self, slot: tuple[str, bool], literal: Literal) -> None:
        self.literals[slot] = literal

    # ---------------------------------------------------------------- valores simples
    def add_value(self, category: str, value: str, label: str | None = None) -> None:
        value = value.strip(" .,;:-|")
        if len(value) < 3 or self.is_excluded(value):
            return
        digits = category in DIGIT_KINDS
        if digits:
            canon = norm_digits(value)
            if sum(c.isdigit() for c in canon) < 3:
                return
            source = fuzzy_digits_pattern(value)
            key = f"{category}:{canon}"
        else:
            source = fuzzy_text_pattern(value)
            key = f"{category}:{norm(value)}"
        existing = self.literals.get((key, False))
        if existing is not None:
            if label and not existing.label:
                existing.label = label
            return
        self._store((key, False), Literal(category, key, value, source, digits=digits, label=label))

    def add_custom(self, term: str) -> None:
        if self.is_excluded(term):
            return
        key = f"CUSTOM:{norm(term)}"
        self._store((key, False), Literal("CUSTOM", key, term, fuzzy_text_pattern(term)))

    # ---------------------------------------------------------------- nombres
    def add_name(self, category: str, raw: str) -> None:
        tokens = parse_name(raw)
        if not tokens:
            return
        full = " ".join(tokens)
        if self.is_excluded(full):
            return
        significant = [t for t in tokens if _significant(t) and not self.is_excluded(t)]
        if not significant:
            return
        sig_norm = {norm(t) for t in significant}

        # ¿Corresponde a una persona ya conocida?
        key = None
        known = [self.token_keys[t] for t in sig_norm if t in self.token_keys]
        if known:
            keys = {k for _, k in known}
            if len(keys) == 1:
                existing_key = keys.pop()
                existing_tokens = self.name_keys[existing_key][1]
                if sig_norm <= existing_tokens or len(sig_norm & existing_tokens) >= 2:
                    key = existing_key
                    category = self.name_keys[existing_key][0]
        if key is None:
            self._counter += 1
            key = f"{category}:{self._counter}"
            self.name_keys[key] = (category, set())
        self.name_keys[key][1].update(sig_norm)

        # Nombre completo como literal (prioridad por longitud)
        if len(tokens) > 1:
            slot = (f"{key}|{norm(full)}", True)
            if slot not in self.literals:
                self._store(slot, Literal(category, key, full, fuzzy_text_pattern(full, r",?\s+"),
                                          name_token=True))

        # Cada apellido/nombre por separado (propagación)
        for token in significant:
            t_norm = norm(token)
            if t_norm in self.token_keys:
                continue
            self.token_keys[t_norm] = (category, key)
            self._store((f"{key}|{t_norm}", True),
                        Literal(category, key, token, fuzzy_text_pattern(token), name_token=True))


def _end_boundary(value: str) -> str:
    """Límite derecho de un literal: tras un dígito basta con que no siga otro dígito."""
    return r"(?![0-9])" if value[-1:].isdigit() else r"(?![\w])"


def _significant(token: str) -> bool:
    plain = token.strip(".,'’-")
    return (len(plain) >= 3 and plain.lower() not in rules.PARTICLES
            and norm(plain) not in _NON_NAME_NORM and not rules.INITIAL_RE.match(token))


_NON_NAME_NORM = {norm(w) for w in rules.NON_NAME_WORDS}
_TITLES_NORM = {norm(w) for w in rules.TITLES}


def parse_name(raw: str) -> list[str]:
    """Extrae la secuencia de tokens que forman un nombre propio al inicio de `raw`."""
    tokens = raw.replace(",", " , ").split()
    out: list[str] = []
    comma_used = False
    # quitar tratamientos iniciales (Dr., Sra., Mr. ...)
    while tokens and norm(tokens[0].rstrip(".")) in _TITLES_NORM:
        tokens.pop(0)
    for tok in tokens:
        if tok == ",":
            if out and not comma_used and len(out) <= 3:
                comma_used = True
                continue
            break
        bare = tok.rstrip(".:;")
        lower = bare.lower()
        if not bare:
            break
        if out and lower in rules.PARTICLES and tok == bare:
            out.append(bare)
            continue
        if rules.INITIAL_RE.match(tok):
            out.append(tok)
            continue
        if not rules.NAME_TOKEN_RE.match(bare) or norm(bare) in _NON_NAME_NORM:
            break
        out.append(bare)
        if tok != bare:  # terminó con punto, dos puntos, etc.
            break
        if len(out) >= 7:
            break
    while out and (out[-1].lower() in rules.PARTICLES):
        out.pop()
    if not any(_significant(t) for t in out):
        return []
    return out


# --------------------------------------------------------------------------- extracción de valores rotulados

_ID_VALUE_RE = re.compile(r"^[A-Za-z]{0,4}[\s.\-]?\d[\dA-Za-z.\-/]*")
# Palabra pegada al final de un identificador por el OCR: "778201Previsión" -> "778201".
_GLUED_WORD_RE = re.compile(r"(?<=\d)[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}.*$")
_PHONE_VALUE_RE = re.compile(r"\+?\(?\d[\d\s().\-]{5,22}\d")


def _cut_value(rest: str) -> str:
    stop = rules.VALUE_STOP_RE.search(rest)
    if stop:
        rest = rest[: stop.start()]
    nxt = rules.NEXT_LABEL_RE.search(rest)
    if nxt and nxt.start() > 0:
        rest = rest[: nxt.start()]
    return rest.strip()


def _match_date(value: str) -> str | None:
    for pattern in rules.DATE_PATTERNS:
        m = pattern.search(value)
        if m and m.start() <= 2:
            return m.group(0)
    return None


def _extract_labeled(knowledge: Knowledge, text: str, opts: Options) -> None:
    """Una sola pasada (regex combinada y precompilada) sobre el texto completo en minúsculas.

    Las reglas no cruzan saltos de línea; si la etiqueta queda sola al final de la línea
    ("Nombre:" + salto), el valor se toma de la línea siguiente.
    """
    length = len(text)
    lowered = rules.lower_same_length(text)
    regex, active = rules.combined_rules(bool(opts.anonymize_professionals),
                                         bool(opts.anonymize_addresses))
    for m in regex.finditer(lowered):
        group = m.lastgroup or "r0"  # siempre hay un grupo con nombre (r0, r1, ...)
        rule = active[int(group[1:])]
        line_end = text.find("\n", m.end())
        line_end = length if line_end < 0 else line_end
        rest = text[m.end():line_end]
        value = _cut_value(rest)
        if not value and not rest.strip() and line_end < length:
            next_end = text.find("\n", line_end + 1)
            value = _cut_value(text[line_end + 1: length if next_end < 0 else next_end])
        if value:
            _register_value(knowledge, rule, value)


def _register_value(knowledge: Knowledge, rule: rules.LabelRule, value: str) -> None:
    kind = rule.kind
    if kind == "name":
        knowledge.add_name(rule.category, value)
    elif kind == "date":
        date = _match_date(value)
        if date:
            knowledge.add_value(rule.category, date)
    elif kind == "id":
        if _match_date(value):
            return
        m = _ID_VALUE_RE.match(_GLUED_WORD_RE.sub("", value))
        if m and sum(c.isdigit() for c in m.group(0)) >= 3:
            knowledge.add_value(rule.category, m.group(0).rstrip(".-/"))
    elif kind == "phone":
        for m in _PHONE_VALUE_RE.finditer(value):
            if sum(c.isdigit() for c in m.group(0)) >= 7:
                knowledge.add_value(rule.category, m.group(0).strip())
    elif kind == "email":
        m = rules.EMAIL_RE.search(value)
        if m:
            knowledge.add_value(rule.category, m.group(0))
    elif kind == "address":
        if any(c.isalpha() for c in value) and len(value) >= 3:
            knowledge.add_value(rule.category, value)
    else:
        knowledge.add_value(rule.category, value)


def build_knowledge(text: str, opts: Options) -> Knowledge:
    excluded = {norm(v) for v in opts.exclude} | {norm_digits(v) for v in opts.exclude if norm_digits(v)}
    knowledge = Knowledge(excluded, opts.whitelist)

    _extract_labeled(knowledge, text, opts)

    if opts.anonymize_professionals:
        for pattern in rules.PROFESSIONAL_PATTERNS:
            for m in pattern.finditer(text):
                knowledge.add_name("PROFESSIONAL", m.group("name"))
    for pattern in rules.PERSON_PATTERNS:
        for m in pattern.finditer(text):
            knowledge.add_name("PERSON", m.group("name"))

    if identifiers.resolver_region(opts.region) is not None:
        for hit in identifiers.contextuales(text):
            category, label = _identifier_category(hit.etiqueta)
            knowledge.add_value(category, hit.texto, label)

    for term in opts.custom_terms:
        knowledge.add_custom(term)
    return knowledge.compile()


def _identifier_category(etiqueta: str) -> tuple[str, str | None]:
    """Etiqueta del módulo de identificadores -> (categoría, marcador específico)."""
    if etiqueta == "FICHA_CLINICA":
        return "RECORD", None  # usa el marcador localizado [N_FICHA] / [RECORD_NO]
    return "ID", etiqueta


# Marcadores específicos que se traducen según el idioma de salida.
LOCALIZED_LABELS = {
    "PASAPORTE": {"es": "PASAPORTE", "en": "PASSPORT"},
    "NUMERO": {"es": "NUMERO", "en": "NUMBER"},
}


# --------------------------------------------------------------------------- redacción

@dataclass
class Span:
    start: int
    end: int
    category: str
    key: str
    label: str | None = None
    rank: int = 2  # desempate ante el mismo texto: menor = más específico

    @property
    def length(self) -> int:
        return self.end - self.start


_DIGIT_RE = re.compile(r"\d")
_URL_HINT_RE = re.compile(r"www\.|https?://", re.IGNORECASE)

_JOINABLE_GAP = re.compile(r"^[\s,]*(?:(?:de|del|la|las|los|y|e|van|von|da|di)[\s,]+)*$", re.IGNORECASE)


class Redactor:
    def __init__(self, knowledge: Knowledge, opts: Options, lang: str):
        self.knowledge = knowledge
        self.opts = opts
        self.lang = lang if lang in PLACEHOLDERS else "es"
        self.countries = identifiers.resolver_region(opts.region)
        self.numbers: dict[tuple[str, str], int] = {}
        self.per_category: dict[str, int] = {}
        self.report: dict[str, dict] = {}

    # ---------------------------------------------------------------- placeholders
    def placeholder(self, category: str, key: str, specific: str | None = None) -> str:
        if specific:
            label = LOCALIZED_LABELS.get(specific, {}).get(self.lang, specific)
        else:
            label = PLACEHOLDERS[self.lang].get(category, category)
        if self.opts.replacement_style == "tag":
            return f"[{label}]"
        number_key = (label, key)
        if number_key not in self.numbers:
            self.per_category[label] = self.per_category.get(label, 0) + 1
            self.numbers[number_key] = self.per_category[label]
        return f"[{label}_{self.numbers[number_key]}]"

    # ---------------------------------------------------------------- spans
    def _literal_spans(self, text: str, spans: list[Span]) -> None:
        kn = self.knowledge
        for matcher in (kn.term_matcher, kn.digit_matcher):
            if matcher is None:
                continue
            for start, end, candidates in matcher.finditer(text):
                upper = text[start].isupper()
                for lit in candidates:
                    if lit.name_token and not upper:
                        continue
                    spans.append(Span(start, end, lit.category, lit.key, lit.label, 1 if lit.label else 2))
                    break
        for regex, table, keyfn in ((kn.text_re, kn.text_lookup, lookup_key),
                                    (kn.digit_re, kn.digit_lookup, norm_digits)):
            if regex is None:
                continue
            for m in regex.finditer(text):
                found = m.group(0)
                for lit in table.get(keyfn(found), ()):
                    if lit.name_token and not found[:1].isupper():
                        continue
                    spans.append(Span(m.start(), m.end(), lit.category, lit.key, lit.label,
                                      1 if lit.label else 2))
                    break

    def _find_spans(self, text: str) -> list[Span]:
        spans: list[Span] = []
        self._literal_spans(text, spans)

        # Filtros rápidos: casi todos los patrones necesitan dígitos, "@" o "www/http".
        has_digit = _DIGIT_RE.search(text) is not None
        if "@" in text:
            self._pattern_spans(text, spans, rules.EMAIL_RE, "EMAIL")
        if _URL_HINT_RE.search(text):
            self._pattern_spans(text, spans, rules.URL_RE, "URL")
        if has_digit:
            self._digit_spans(text, spans)
        if (self.countries is not None or self.opts.aggressive_numbers) and \
                rules.ID_CANDIDATE_RE.search(text):
            self._identifier_spans(text, spans)

        wl = self.knowledge.whitelist_re
        if wl is not None and spans:
            allowed = [(m.start(), m.end()) for m in wl.finditer(text)]
            if allowed:
                spans = [s for s in spans if not any(a <= s.start and s.end <= b for a, b in allowed)]
        return spans

    def _pattern_spans(self, text, spans, regex, category, digits=False):
        excluded = self.knowledge.is_excluded
        for m in regex.finditer(text):
            value = m.group(0)
            if excluded(value):
                continue
            key = f"{category}:{norm_digits(value) if digits else norm(value)}"
            spans.append(Span(m.start(), m.end(), category, key))

    def _digit_spans(self, text: str, spans: list[Span]) -> None:
        add_pattern = functools.partial(self._pattern_spans, text, spans)
        if rules.IP_HINT_RE.search(text):
            add_pattern(rules.IP_RE, "IP")
        if rules.ID_CANDIDATE_RE.search(text):
            for regex in rules.ID_PATTERNS:
                add_pattern(regex, "ID", digits=True)
            for regex in rules.PHONE_PATTERNS:
                add_pattern(regex, "PHONE", digits=True)
        if self.opts.anonymize_addresses:
            for regex in rules.ADDRESS_PATTERNS:
                add_pattern(regex, "ADDRESS")
        if self.opts.anonymize_all_dates:
            for regex in rules.DATE_PATTERNS:
                add_pattern(regex, "DATE")

    def _identifier_spans(self, text: str, spans: list[Span]) -> None:
        excluded = self.knowledge.is_excluded
        # Identificadores por país (validados con dígito verificador cuando existe).
        hits = identifiers.estructurales(text, self.countries) if self.countries is not None else []
        if self.opts.aggressive_numbers:
            hits += identifiers.agresivos(text)
        for hit in hits:
            if excluded(hit.texto):
                continue
            category, label = _identifier_category(hit.etiqueta)
            rank = 3 if hit.capa == "agresiva" else 0
            spans.append(Span(hit.inicio, hit.fin, category, f"{category}:{norm_digits(hit.texto)}",
                              label, rank))

    @staticmethod
    def _resolve(spans: list[Span]) -> list[Span]:
        # A igual longitud gana lo más específico. La capa agresiva (rank 3, "[NUMERO]") siempre
        # pierde frente a un dato reconocido (p. ej. N° de ficha), sea cual sea su categoría.
        spans.sort(key=lambda s: (-s.length, s.rank >= 3, CATEGORY_PRIORITY.get(s.category, 99),
                                  s.rank, s.start))
        chosen: list[Span] = []
        for span in spans:
            if all(span.end <= c.start or span.start >= c.end for c in chosen):
                chosen.append(span)
        chosen.sort(key=lambda s: s.start)
        return chosen

    def _merge_names(self, text: str, spans: list[Span]) -> list[Span]:
        merged: list[Span] = []
        for span in spans:
            if (merged and span.category in NAME_CATEGORIES and merged[-1].key == span.key
                    and _JOINABLE_GAP.match(text[merged[-1].end:span.start])):
                merged[-1] = Span(merged[-1].start, span.end, span.category, span.key)
            else:
                merged.append(span)
        return merged

    def redact(self, text: str) -> str:
        if not text or not text.strip():
            return text
        spans = self._merge_names(text, self._resolve(self._find_spans(text)))
        if not spans:
            return text
        out, pos = [], 0
        for span in spans:
            original = text[span.start:span.end]
            replacement = self.placeholder(span.category, span.key, span.label)
            out.append(text[pos:span.start])
            out.append(replacement)
            pos = span.end
            report_key = replacement if self.opts.replacement_style != "tag" else f"{replacement}|{span.key}"
            entry = self.report.setdefault(report_key, {
                "category": span.category, "placeholder": replacement,
                "values": [], "count": 0,
            })
            entry["count"] += 1
            clean = " ".join(original.split())
            if clean not in entry["values"]:
                entry["values"].append(clean)
        out.append(text[pos:])
        return "".join(out)

    def entities(self) -> list[dict]:
        items = sorted(self.report.values(),
                       key=lambda e: (CATEGORY_PRIORITY.get(e["category"], 99), e["placeholder"]))
        return [dict(e) for e in items]
