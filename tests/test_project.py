"""Coherencia del proyecto: versión única, changelog y punto de entrada."""

import json
import re
from pathlib import Path

import main
from anonymizer import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.]+)?", __version__)


def test_frontend_version_matches_backend():
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == __version__


def test_changelog_mentions_current_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog
    assert "## [Unreleased]" in changelog


def test_spec_reads_version_from_package():
    spec = (ROOT / "anonimize.spec").read_text(encoding="utf-8")
    assert "__version__" in spec and "version=str(VERSION_FILE)" in spec


def test_parse_args_defaults():
    config = main.parse_args([])
    assert not config.dev and not config.self_test


def test_self_test_passes_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "find_frontend", lambda: tmp_path / "index.html")
    report = tmp_path / "report.json"
    assert main.main(["--self-test", "--self-test-report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["ok"] and data["version"] == __version__
    assert all(data["checks"].values())


def test_self_test_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "find_frontend", lambda: None)  # interfaz no empaquetada
    report = tmp_path / "report.json"
    assert main.main(["--self-test", "--self-test-report", str(report)]) == 1
    assert json.loads(report.read_text(encoding="utf-8"))["checks"]["frontend_bundled"] is False
