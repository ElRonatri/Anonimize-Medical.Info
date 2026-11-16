"""Notas de un release a partir de CHANGELOG.md y verificación de versión.

Uso:
    python scripts/release_notes.py version             # imprime __version__
    python scripts/release_notes.py check v1.1.0        # el tag coincide con __version__ y el CHANGELOG
    python scripts/release_notes.py notes 1.1.0         # sección del CHANGELOG para esa versión
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    text = (ROOT / "backend" / "anonymizer" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("No se encontró __version__")
    return match.group(1)


def notes(ver: str, changelog: Path = ROOT / "CHANGELOG.md") -> str:
    text = changelog.read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(ver)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    if not match or not match.group(1).strip():
        raise SystemExit(f"CHANGELOG.md no tiene una sección para la versión {ver}")
    return match.group(1).strip() + "\n"


def check(tag: str) -> str:
    ver = version()
    if tag.removeprefix("v") != ver:
        raise SystemExit(f"El tag {tag} no coincide con __version__ = {ver}")
    notes(ver)
    return ver


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command, *rest = argv
    if command == "version":
        print(version())
    elif command == "check":
        print(check(rest[0]))
    elif command == "notes":
        sys.stdout.write(notes(rest[0] if rest else version()))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
