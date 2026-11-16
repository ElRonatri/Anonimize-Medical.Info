"""Hashes de release (scripts/checksums.py) y notas/versión (scripts/release_notes.py)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import checksums
import release_notes

ROOT = Path(__file__).resolve().parent.parent


def _files(tmp_path: Path) -> Path:
    folder = tmp_path / "release"
    folder.mkdir()
    (folder / "AnonimizeMedical-1.0.0-windows-base.zip").write_bytes(b"base" * 1000)
    (folder / "AnonimizeMedical-1.0.0-windows-ocr.zip").write_bytes(b"ocr" * 5000)
    (folder / "notas.txt").write_text("no se suma", encoding="utf-8")
    return folder


def test_create_matches_hashlib_and_sha256sum_format(tmp_path):
    folder = _files(tmp_path)
    assert checksums.main(["create", str(folder)]) == 0
    lines = (folder / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert [line.split("  ")[1] for line in lines] == [
        "AnonimizeMedical-1.0.0-windows-base.zip", "AnonimizeMedical-1.0.0-windows-ocr.zip"]
    for line in lines:
        digest, name = line.split("  ")
        assert digest == hashlib.sha256((folder / name).read_bytes()).hexdigest()
    assert checksums.main(["verify", str(folder / "SHA256SUMS.txt")]) == 0


def test_verify_detects_tampering_and_missing_files(tmp_path):
    folder = _files(tmp_path)
    checksums.main(["create", str(folder)])
    (folder / "AnonimizeMedical-1.0.0-windows-ocr.zip").write_bytes(b"alterado")
    (folder / "AnonimizeMedical-1.0.0-windows-base.zip").unlink()
    errors = checksums.verify(folder / "SHA256SUMS.txt")
    assert any("ocr.zip: la suma no coincide" in e for e in errors)
    assert any("base.zip: no existe" in e for e in errors)
    assert checksums.main(["verify", str(folder / "SHA256SUMS.txt")]) == 1


def test_verify_rejects_paths_outside_the_folder(tmp_path):
    folder = _files(tmp_path)
    (folder / "SHA256SUMS.txt").write_text(f"{'0' * 64}  ../secreto.zip\n", encoding="utf-8")
    assert checksums.verify(folder / "SHA256SUMS.txt") == ["../secreto.zip: ruta no permitida"]


def test_release_version_and_notes():
    version = release_notes.version()
    assert release_notes.check(f"v{version}") == version
    assert release_notes.notes(version).strip()
    with pytest.raises(SystemExit):
        release_notes.check("v0.0.0-no-existe")


def test_notes_require_changelog_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [2.0.0] - 2027-01-01\n\n### Añadido\n- Algo.\n\n## [1.0.0]\n- Antes.\n",
                         encoding="utf-8")
    assert release_notes.notes("2.0.0", changelog) == "### Añadido\n- Algo.\n"
    with pytest.raises(SystemExit):
        release_notes.notes("3.0.0", changelog)


def test_workflows_publish_checksums_and_sign_before_hashing():
    build = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "scripts/checksums.py create" in build
    # La firma (cuando se active) debe ir antes del ZIP y de la suma.
    assert build.index("docs/signing.md") < build.index("Compress-Archive")
    assert "SHA256SUMS.txt" in release and "--verify-tag" in release
    jobs = release.split("\njobs:\n")[1]
    assert "contents: write" in jobs.split("\n  publish:\n")[1]  # sólo el job que publica
    assert "contents: write" not in jobs.split("\n  publish:\n")[0]
