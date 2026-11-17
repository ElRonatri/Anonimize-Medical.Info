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
    assert "SHA256SUMS.txt" in release and "scripts/publish_release.sh" in release
    jobs = release.split("\njobs:\n")[1]
    assert "contents: write" in jobs.split("\n  publish:\n")[1]  # sólo el job que publica
    assert "contents: write" not in jobs.split("\n  publish:\n")[0]


# --------------------------------------------------------------------------- publicación

FAKE_GH = r"""#!/usr/bin/env bash
# gh simulado: el estado viene de variables de entorno y cada llamada queda en $GH_LOG.
echo "gh $*" >> "$GH_LOG"
case "$1 $2" in
  "release view") [ -n "$FAKE_DRAFT" ] && { echo "$FAKE_DRAFT"; exit 0; } || exit 1 ;;
  "api repos/"*) [ -n "$FAKE_TAG_SHA" ] && { echo "$FAKE_TAG_SHA"; exit 0; } || exit 1 ;;
esac
exit 0
"""


def publish(tmp_path, *, draft="", tag_sha="", ref="refs/heads/main", sha="abc123"):
    import shutil
    import subprocess

    if shutil.which("bash") is None:
        pytest.skip("bash no disponible")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(FAKE_GH, encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    rel = tmp_path / "release"
    rel.mkdir()
    (rel / "AnonimizeMedical-1.1.0-windows-base.zip").write_bytes(b"zip")
    (rel / "SHA256SUMS.txt").write_text("x", encoding="utf-8")
    (tmp_path / "notes.md").write_text("notas", encoding="utf-8")
    log = tmp_path / "gh.log"
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "GH_LOG": str(log), "FAKE_DRAFT": draft,
           "FAKE_TAG_SHA": tag_sha, "VERSION": "1.1.0", "GITHUB_SHA": sha, "GITHUB_REF": ref,
           "GITHUB_REPOSITORY": "dueno/repo"}
    res = subprocess.run(["bash", str(ROOT / "scripts" / "publish_release.sh"), str(rel), str(tmp_path / "notes.md")],
                         env=env, capture_output=True, text=True, timeout=60)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return res, [c for c in calls if not c.startswith(("gh release view", "gh api"))]


def test_publish_with_existing_tag(tmp_path):
    res, calls = publish(tmp_path, tag_sha="abc123", ref="refs/tags/v1.1.0")
    assert res.returncode == 0, res.stderr
    assert len(calls) == 1 and "release create v1.1.0" in calls[0] and "--verify-tag" in calls[0]
    assert "SHA256SUMS.txt" in calls[0] and "windows-base.zip" in calls[0]


def test_publish_from_main_creates_tag_at_built_commit(tmp_path):
    res, calls = publish(tmp_path)
    assert res.returncode == 0, res.stderr
    assert len(calls) == 1 and "--target abc123" in calls[0] and "--verify-tag" not in calls[0]


def test_publish_completes_existing_draft(tmp_path):
    res, calls = publish(tmp_path, draft="true")
    assert res.returncode == 0, res.stderr
    assert calls[0].startswith("gh release upload v1.1.0") and "--clobber" in calls[0]
    assert calls[1].startswith("gh release edit v1.1.0")
    assert "--draft=false" in calls[1] and "--target abc123" in calls[1]


@pytest.mark.parametrize("kwargs,message", [
    ({"draft": "false"}, "ya está publicado"),
    ({"ref": "refs/heads/otra-rama"}, "sólo se crea al publicar desde main"),
    ({"tag_sha": "otro999"}, "no al commit compilado"),
    ({"draft": "true", "tag_sha": "otro999"}, "no al commit compilado"),
])
def test_publish_refuses_unsafe_cases(tmp_path, kwargs, message):
    res, calls = publish(tmp_path, **kwargs)
    assert res.returncode == 1 and message in res.stderr
    assert calls == []  # no se creó ni modificó nada
