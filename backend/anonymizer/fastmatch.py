r"""Búsqueda de muchos términos en una sola pasada (Aho-Corasick).

Se usa para propagar nombres y apellidos: con miles de términos distintos, una regex con
alternativas cuesta O(longitud × términos); Aho-Corasick cuesta O(longitud + coincidencias).

Equivalencia con las regex "difusas" del detector:
* insensible a mayúsculas y tildes (á→a, ñ→n, ç→c, ...);
* todo espacio en blanco equivale a un espacio; "/", "." y "-" son equivalentes;
* entre palabras, cualquier secuencia de espacios y comas equivale a un espacio
  ("Johnson, Robert L." coincide con el nombre "Johnson Robert L."), como hacía la
  regex `,?\s+` de los nombres completos;
* el texto se "pliega" carácter a carácter SIN cambiar su longitud, así que las posiciones
  encontradas valen sobre el texto original (donde se verifican límites de palabra y la
  mayúscula inicial de los nombres).

Requiere `pyahocorasick` (BSD-3-Clause, ~115 KB). Si no está instalado, el detector usa regex.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Iterator
from typing import Any

try:
    import ahocorasick

    AVAILABLE = True
except ImportError:  # pragma: no cover - depende del entorno
    ahocorasick = None
    AVAILABLE = False

_SEPARATORS = {"/": "/", ".": "/", "-": "/"}


class _FoldTable(dict[int, str]):
    """Tabla para str.translate que calcula (y memoriza) el plegado de cada carácter."""

    def __missing__(self, code: int) -> str:
        ch = chr(code)
        if ch.isspace():
            folded = " "
        elif ch in _SEPARATORS:
            folded = _SEPARATORS[ch]
        else:
            base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            lowered = base.lower()
            folded = lowered if len(lowered) == 1 else (ch.lower() if len(ch.lower()) == 1 else ch)
        self[code] = folded
        return folded


_FOLD = _FoldTable()


def fold(text: str) -> str:
    """Plegado de igual longitud: minúsculas, sin tildes, espacios y separadores unificados."""
    return text.translate(_FOLD)


def fold_key(value: str) -> str:
    """Clave de búsqueda de un término: plegado + espacios y comas colapsados."""
    return " ".join(fold(value).replace(",", " ").split())


# Modo texto: secuencias de espacios/comas que NO son exactamente un espacio -> " ".
_TEXT_GAP_RE = re.compile(r"[ ,]*,[ ,]*| {2,}")
# Modo dígitos: separadores dentro de identificadores (ya plegados: "." y "-" son "/") -> "".
_DIGIT_GAP_RE = re.compile(r"[ /()]+")
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]")


class _Compressed:
    """Texto plegado con ciertos huecos reemplazados (por " " o eliminados).

    Guarda los puntos de corte para traducir posiciones al texto original.
    """

    __slots__ = ("text", "_starts", "_deltas", "_bisect")

    def __init__(self, folded: str, gap: re.Pattern[str], replacement: str) -> None:
        starts: list[int] = []  # posición comprimida de cada hueco
        deltas: list[int] = []  # caracteres eliminados acumulados DESPUÉS de cada hueco
        delta = 0
        for m in gap.finditer(folded):
            starts.append(m.start() - delta)
            delta += (m.end() - m.start()) - len(replacement)
            deltas.append(delta)
        self._starts, self._deltas = starts, deltas
        self.text = gap.sub(replacement, folded) if starts else folded
        # Si el hueco se reemplaza por un espacio, éste ocupa su posición comprimida; si se
        # elimina, en esa posición queda el carácter siguiente (que ya va "desplazado").
        self._bisect = bisect.bisect_left if replacement else bisect.bisect_right

    def original(self, index: int) -> int:
        """Posición original de un carácter que NO es parte de un hueco."""
        k = self._bisect(self._starts, index) - 1
        return index + (self._deltas[k] if k >= 0 else 0)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class TermMatcher:
    """Autómata con todos los términos; cada término lleva una carga útil (payload).

    `digits=True`: para identificadores. Se comparan sólo letras y dígitos, ignorando
    espacios, puntos, guiones, barras y paréntesis ("12.345.678-5" == "123456785").
    """

    def __init__(self, digits: bool = False) -> None:
        if not AVAILABLE:
            raise RuntimeError("pyahocorasick no está instalado")
        self.digits = digits
        self._automaton = ahocorasick.Automaton()
        self._payloads: dict[str, list[Any]] = {}
        self._built = False

    def add(self, term: str, payload: Any) -> None:
        key = _NON_ALNUM_RE.sub("", fold(term)) if self.digits else fold_key(term)
        if not key:
            return
        bucket = self._payloads.setdefault(key, [])
        bucket.append(payload)
        if len(bucket) == 1:
            self._automaton.add_word(key, (len(key), key))

    def __len__(self) -> int:
        return len(self._payloads)

    def build(self) -> TermMatcher:
        if self._payloads:
            self._automaton.make_automaton()
        self._built = True
        return self

    def finditer(self, text: str) -> Iterator[tuple[int, int, list[Any]]]:
        """(inicio, fin, payloads) de cada coincidencia con límites de palabra.

        Devuelve TODAS las coincidencias, incluso solapadas; la resolución de solapamientos
        del detector elige luego la más larga.
        """
        if not self._payloads:
            return
        if self.digits:
            compressed = _Compressed(fold(text), _DIGIT_GAP_RE, "")
        else:
            compressed = _Compressed(fold(text), _TEXT_GAP_RE, " ")
        n = len(text)
        for end_index, (length, key) in self._automaton.iter(compressed.text):
            start = compressed.original(end_index - length + 1)
            end = compressed.original(end_index) + 1
            if start > 0 and _is_word_char(text[start - 1]):
                continue
            if end < n and (text[end].isdigit() if key[-1:].isdigit() else _is_word_char(text[end])):
                continue  # valores que terminan en dígito: basta con que no siga otro dígito (OCR)
            yield start, end, self._payloads[key]
