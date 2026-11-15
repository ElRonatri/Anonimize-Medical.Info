"""Detección de datos personales y reemplazo por marcadores."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import rules
from .lang import PLACEHOLDERS

NAME_CATEGORIES = ("PATIENT", "PERSON", "PROFESSIONAL")
CATEGORY_PRIORITY = {c: i for i, c in enumerate(
    ("PATIENT", "BIRTHDATE", "ID", "RECORD", "PERSON", "PHONE", "EMAIL", "ADDRESS",
     "PROFESSIONAL", "CUSTOM", "URL", "IP", "DATE"))}

DIGIT_KINDS = {"ID", "RECORD", "PHONE"}


# --------------------------------------------------------------------------- normalización

def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm(text: str) -> str:
    return " ".join(strip_accents(text).lower().split())


def norm_digits(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", strip_accents(text).lower())


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
    custom_terms: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Options":
        data = data or {}
        opts = cls()
        for key, value in data.items():
            if hasattr(opts, key) and value is not None:
                setattr(opts, key, value)
        opts.custom_terms = [t.strip() for t in (opts.custom_terms or []) if t and t.strip()]
        opts.exclude = [t for t in (opts.exclude or []) if t]
        return opts


# --------------------------------------------------------------------------- conocimiento

@dataclass
class Literal:
    category: str
    key: str
    value: str
    pattern: re.Pattern
    name_token: bool = False  # exige mayúscula inicial en la coincidencia


class Knowledge:
    """Valores concretos detectados en el documento (nombres, IDs, fechas...)."""

    def __init__(self, excluded: set[str]):
        self.excluded = excluded
        self.literals: dict[tuple[str, bool], Literal] = {}
        self.token_keys: dict[str, tuple[str, str]] = {}  # token normalizado -> (cat, key)
        self.name_keys: dict[str, tuple[str, set[str]]] = {}  # key -> (cat, tokens)
        self._counter = 0

    def is_excluded(self, value: str) -> bool:
        return norm(value) in self.excluded or norm_digits(value) in self.excluded

    # ---------------------------------------------------------------- valores simples
    def add_value(self, category: str, value: str) -> None:
        value = value.strip(" .,;:-|")
        if len(value) < 3 or self.is_excluded(value):
            return
        if category in DIGIT_KINDS:
            canon = norm_digits(value)
            if sum(c.isdigit() for c in canon) < 3:
                return
            pattern = fuzzy_digits_pattern(value)
            key = f"{category}:{canon}"
        else:
            pattern = fuzzy_text_pattern(value)
            key = f"{category}:{norm(value)}"
        if (key, False) in self.literals:
            return
        regex = re.compile(rf"(?<![\w]){pattern}(?![\w])", re.IGNORECASE)
        self.literals[(key, False)] = Literal(category, key, value, regex)

    # ---------------------------------------------------------------- nombres
    def add_name(self, category: str, raw: str) -> None:
        tokens = parse_name(raw)
        if not tokens:
            return
        full = " ".join(tokens)
        if self.is_excluded(full):
            return
        significant = [t for t in tokens if _significant(t)]
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
            lit_key = (f"{key}|{norm(full)}", True)
            if lit_key not in self.literals:
                regex = re.compile(rf"(?<![\w]){fuzzy_text_pattern(full, r',?\s+')}(?![\w])",
                                   re.IGNORECASE)
                self.literals[lit_key] = Literal(category, key, full, regex, name_token=True)

        # Cada apellido/nombre por separado (propagación)
        for token in significant:
            t_norm = norm(token)
            if t_norm in self.token_keys or self.is_excluded(token):
                continue
            self.token_keys[t_norm] = (category, key)
            regex = re.compile(rf"(?<![\w]){fuzzy_text_pattern(token)}(?![\w])", re.IGNORECASE)
            self.literals[(f"{key}|{t_norm}", True)] = Literal(category, key, token, regex, name_token=True)


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
    lines = text.split("\n")
    for index, line in enumerate(lines):
        for rule, regex in rules.COMPILED_RULES:
            if rule.category == "PROFESSIONAL" and not opts.anonymize_professionals:
                continue
            if rule.category == "ADDRESS" and not opts.anonymize_addresses:
                continue
            for m in regex.finditer(line):
                value = _cut_value(line[m.end():])
                if not value and index + 1 < len(lines) and line[m.end():].strip() == "":
                    value = _cut_value(lines[index + 1])
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
        m = _ID_VALUE_RE.match(value)
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
    knowledge = Knowledge(excluded)

    _extract_labeled(knowledge, text, opts)

    if opts.anonymize_professionals:
        for pattern in rules.PROFESSIONAL_PATTERNS:
            for m in pattern.finditer(text):
                knowledge.add_name("PROFESSIONAL", m.group("name"))
    for pattern in rules.PERSON_PATTERNS:
        for m in pattern.finditer(text):
            knowledge.add_name("PERSON", m.group("name"))

    for term in opts.custom_terms:
        if not knowledge.is_excluded(term):
            key = f"CUSTOM:{norm(term)}"
            regex = re.compile(rf"(?<![\w]){fuzzy_text_pattern(term)}(?![\w])", re.IGNORECASE)
            knowledge.literals[(key, False)] = Literal("CUSTOM", key, term, regex)
    return knowledge


# --------------------------------------------------------------------------- redacción

@dataclass
class Span:
    start: int
    end: int
    category: str
    key: str

    @property
    def length(self) -> int:
        return self.end - self.start


_JOINABLE_GAP = re.compile(r"^[\s,]*(?:(?:de|del|la|las|los|y|e|van|von|da|di)[\s,]+)*$", re.IGNORECASE)


class Redactor:
    def __init__(self, knowledge: Knowledge, opts: Options, lang: str):
        self.knowledge = knowledge
        self.opts = opts
        self.lang = lang if lang in PLACEHOLDERS else "es"
        self.numbers: dict[str, int] = {}
        self.per_category: dict[str, int] = {}
        self.report: dict[str, dict] = {}

    # ---------------------------------------------------------------- placeholders
    def placeholder(self, category: str, key: str) -> str:
        label = PLACEHOLDERS[self.lang].get(category, category)
        if self.opts.replacement_style == "tag":
            return f"[{label}]"
        if key not in self.numbers:
            self.per_category[category] = self.per_category.get(category, 0) + 1
            self.numbers[key] = self.per_category[category]
        return f"[{label}_{self.numbers[key]}]"

    # ---------------------------------------------------------------- spans
    def _find_spans(self, text: str) -> list[Span]:
        spans: list[Span] = []
        excluded = self.knowledge.is_excluded

        for lit in self.knowledge.literals.values():
            for m in lit.pattern.finditer(text):
                if lit.name_token and not m.group(0)[:1].isupper():
                    continue
                spans.append(Span(m.start(), m.end(), lit.category, lit.key))

        def add_pattern(regex, category, digits=False):
            for m in regex.finditer(text):
                value = m.group(0)
                if excluded(value):
                    continue
                key = f"{category}:{norm_digits(value) if digits else norm(value)}"
                spans.append(Span(m.start(), m.end(), category, key))

        add_pattern(rules.EMAIL_RE, "EMAIL")
        add_pattern(rules.URL_RE, "URL")
        add_pattern(rules.IP_RE, "IP")
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
        return spans

    @staticmethod
    def _resolve(spans: list[Span]) -> list[Span]:
        spans.sort(key=lambda s: (-s.length, CATEGORY_PRIORITY.get(s.category, 99), s.start))
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
            replacement = self.placeholder(span.category, span.key)
            out.append(text[pos:span.start])
            out.append(replacement)
            pos = span.end
            entry = self.report.setdefault(span.key, {
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
