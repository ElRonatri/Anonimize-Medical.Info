"""Sumas SHA-256 de los archivos de un release (formato compatible con `sha256sum`).

Uso:
    python scripts/checksums.py create dist/release -o dist/release/SHA256SUMS.txt
    python scripts/checksums.py verify dist/release/SHA256SUMS.txt

Para que un usuario verifique una descarga en Windows (sin Python):
    Get-FileHash .\\AnonimizeMedical-1.0.0-windows-base.zip -Algorithm SHA256
    certutil -hashfile AnonimizeMedical-1.0.0-windows-base.zip SHA256
y comparar con la línea correspondiente de SHA256SUMS.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

CHUNK = 1024 * 1024
SUMS_NAME = "SHA256SUMS.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def create(folder: Path, output: Path, patterns: list[str]) -> list[str]:
    files = sorted({p for pattern in patterns for p in folder.glob(pattern)
                    if p.is_file() and p.name != SUMS_NAME and p.resolve() != output.resolve()})
    if not files:
        raise SystemExit(f"No hay archivos que sumar en {folder}")
    # "<hash>  <nombre>": dos espacios = modo binario, como `sha256sum`.
    lines = [f"{sha256(p)}  {p.name}" for p in files]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return lines


def verify(sums: Path) -> list[str]:
    """Devuelve la lista de errores (vacía si todo coincide)."""
    errors = []
    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            expected, name = line.split(None, 1)
        except ValueError:
            errors.append(f"línea {number}: formato inválido")
            continue
        name = name.lstrip("*").strip()
        target = sums.parent / name
        if Path(name).name != name:
            errors.append(f"{name}: ruta no permitida")
        elif not target.is_file():
            errors.append(f"{name}: no existe")
        elif sha256(target) != expected.lower():
            errors.append(f"{name}: la suma no coincide")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("folder", type=Path)
    c.add_argument("-o", "--output", type=Path)
    c.add_argument("--pattern", action="append", default=None, help="por defecto *.zip")
    v = sub.add_parser("verify")
    v.add_argument("sums", type=Path)
    args = parser.parse_args(argv)

    if args.command == "create":
        output = args.output or args.folder / SUMS_NAME
        for line in create(args.folder, output, args.pattern or ["*.zip"]):
            print(line)
        return 0
    errors = verify(args.sums)
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    if not errors:
        print("OK: todas las sumas coinciden")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
