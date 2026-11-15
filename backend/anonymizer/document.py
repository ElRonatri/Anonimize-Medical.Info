"""Modelo intermedio de documento: páginas compuestas por bloques de líneas y tablas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str  # "line" | "table"
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)

    def pieces(self) -> list[str]:
        if self.kind == "table":
            return [cell for row in self.rows for cell in row]
        return [self.text]

    def flat_text(self) -> str:
        if self.kind == "table":
            return "\n".join(" | ".join(row) for row in self.rows)
        return self.text


@dataclass
class Page:
    number: int
    blocks: list[Block] = field(default_factory=list)
    ocr: bool = False

    @property
    def empty(self) -> bool:
        return not any(b.flat_text().strip() for b in self.blocks)


@dataclass
class Document:
    name: str
    pages: list[Page] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ocr_engine: str | None = None

    def full_text(self) -> str:
        return "\n".join(b.flat_text() for p in self.pages for b in p.blocks)
