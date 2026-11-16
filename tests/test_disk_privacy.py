"""Rastros en disco: preferencias acotadas, perfil de WebView2 efímero, sin temporales ni logs."""

from __future__ import annotations

import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

import appdata
import main
from anonymizer import privacy
from api import Api

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "Zxqwerty Centinela Vadremkuz"  # token sin letras ambiguas para el OCR


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(appdata.ENV_DATA_DIR, str(tmp_path / "datos"))
    return tmp_path / "datos"


# --------------------------------------------------------------------------- preferencias

def test_prefs_roundtrip_and_location(data_dir):
    store = appdata.PrefStore()
    assert store.path == data_dir / "prefs.json"
    assert store.load() == {}
    assert store.set("theme", "dark") and store.set("uiLanguage", "en")
    assert store.set("options", {"region": "CL", "ner": True, "max_workers": 2, "whitelist": ["Hospital Regional"]})
    assert appdata.PrefStore().load() == {
        "theme": "dark", "uiLanguage": "en",
        "options": {"region": "CL", "ner": True, "max_workers": 2, "whitelist": ["Hospital Regional"]},
    }
    assert not list(data_dir.glob("*.tmp"))  # escritura atómica sin restos


@pytest.mark.parametrize("key,value", [
    ("documento", "Paciente: " + SENTINEL),  # clave desconocida
    ("theme", SENTINEL),  # valor fuera de la lista
    ("uiLanguage", "fr"),
    ("responsibleUseDismissed", "sí"),
    ("options", "no es objeto"),
])
def test_prefs_reject_anything_not_allowed(data_dir, key, value):
    store = appdata.PrefStore()
    assert store.set(key, value) is False
    assert not store.path.exists() or SENTINEL not in store.path.read_text(encoding="utf-8")


def test_options_drop_session_terms_and_free_text(data_dir):
    store = appdata.PrefStore()
    store.set("options", {
        "custom_terms": [SENTINEL],  # términos a ocultar: nunca se guardan
        "region": "CL; " + SENTINEL,  # no es un token
        "language": "es",
        "whitelist": ["ok", "x" * 500],  # demasiado largo: se descarta la lista completa
        "max_workers": 999,
        "ner_threshold": 0.9,
        "texto": SENTINEL,
    })
    assert store.load()["options"] == {"language": "es", "ner_threshold": 0.9}
    assert SENTINEL not in store.path.read_text(encoding="utf-8")


def test_corrupt_or_tampered_prefs_file_is_sanitized(data_dir):
    data_dir.mkdir(parents=True)
    path = data_dir / "prefs.json"
    path.write_text("{no json", encoding="utf-8")
    assert appdata.PrefStore().load() == {}
    path.write_text(json.dumps({"theme": "light", "nota": SENTINEL}), encoding="utf-8")
    assert appdata.PrefStore().load() == {"theme": "light"}


def test_api_prefs(data_dir):
    api = Api()
    assert api.get_prefs() == {"ok": True, "prefs": {}}
    assert api.set_pref("theme", "dark") == {"ok": True}
    assert api.set_pref("clinico", SENTINEL)["ok"] is False
    assert api.get_prefs()["prefs"] == {"theme": "dark"}


def test_default_paths_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv(appdata.ENV_DATA_DIR, raising=False)
    monkeypatch.setattr(appdata.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert appdata.prefs_path() == tmp_path / "Roaming" / "AnonimizeMedical" / "prefs.json"
    assert appdata.webview_profile_dir() == tmp_path / "Local" / "AnonimizeMedical" / "WebView2"


# --------------------------------------------------------------------------- perfil de WebView2

def test_cleanup_profile_removes_leftovers(tmp_path):
    profile = tmp_path / "WebView2"
    (profile / "EBWebView" / "Crashpad" / "reports").mkdir(parents=True)
    (profile / "EBWebView" / "Crashpad" / "reports" / "dump.dmp").write_bytes(SENTINEL.encode("utf-16-le"))
    assert appdata.cleanup_webview_profile(profile, delay=0) is True
    assert not profile.exists()
    assert appdata.cleanup_webview_profile(profile, delay=0) is True  # ya no existe


def test_webview2_args_disable_crash_reports():
    env: dict[str, str] = {}
    appdata.configure_webview2_environment(env)
    args = env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"].split()
    assert "--disable-breakpad" in args and "--disable-crash-reporter" in args
    assert "--disable-features=ElasticOverscroll" in args  # el de pywebview se conserva


class FakeWebview(types.ModuleType):
    def __init__(self, fail: bool = False) -> None:
        super().__init__("webview")
        self.fail, self.start_kwargs, self.windows = fail, None, []

    def create_window(self, *args, **kwargs):
        window = types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Event()), kwargs=kwargs)
        self.windows.append(window)
        return window

    def start(self, **kwargs):
        self.start_kwargs = kwargs
        Path(kwargs["storage_path"], "EBWebView").mkdir(parents=True)  # WebView2 crea su perfil
        if self.fail:
            raise RuntimeError("fallo simulado")


class _Event:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


@pytest.mark.parametrize("fail", [False, True])
def test_run_window_private_profile_cleaned_before_and_after(data_dir, monkeypatch, fail):
    fake = FakeWebview(fail)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(main, "find_frontend", lambda: Path("index.html"))
    monkeypatch.delenv("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", raising=False)
    profile = appdata.webview_profile_dir()
    (profile / "restos-de-un-fallo").mkdir(parents=True)

    config = main.parse_args([])
    if fail:
        with pytest.raises(RuntimeError):
            main.run_window(config)
    else:
        main.run_window(config)
    assert fake.start_kwargs["private_mode"] is True
    assert fake.start_kwargs["storage_path"] == str(profile)
    assert fake.start_kwargs["debug"] is False
    assert not profile.exists()  # borrado al cerrar, también si la ventana falló
    assert "--disable-breakpad" in os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"]


# --------------------------------------------------------------------------- volcados de memoria

def test_limit_crash_dumps(monkeypatch):
    monkeypatch.setattr(privacy, "is_windows", lambda: False)
    assert privacy.limit_crash_dumps() is False
    calls = []

    class Wer:
        def WerSetFlags(self, flags):  # noqa: N802 (API de Windows)
            calls.append(flags)
            return 0

    import ctypes

    monkeypatch.setattr(privacy, "is_windows", lambda: True)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name: Wer(), raising=False)
    assert privacy.limit_crash_dumps() is True
    assert calls == [privacy.WER_FAULT_REPORTING_FLAG_NOHEAP]


# --------------------------------------------------------------------------- sin temporales ni logs a disco

def test_backend_never_writes_temp_files_or_log_files():
    offenders = []
    for path in (ROOT / "backend").rglob("*.py"):
        code = path.read_text(encoding="utf-8")
        if re.search(r"\btempfile\b|mkstemp|gettempdir|FileHandler|RotatingFileHandler|faulthandler", code):
            offenders.append(path.name)
    assert not offenders, offenders


def test_build_is_onedir_without_temp_extraction():
    spec = (ROOT / "anonimize.spec").read_text(encoding="utf-8")
    assert "exclude_binaries=True" in spec and "COLLECT(" in spec  # onedir: no hay _MEI* en %TEMP%


# --------------------------------------------------------------------------- sonda (con ventana simulada)

def test_privacy_probe_end_to_end_with_fake_window(data_dir, tmp_path, monkeypatch):
    """La sonda completa con la API real (OCR en paralelo incluido); sólo la ventana es simulada."""
    import privacy_probe

    class Window:
        def evaluate_js(self, script):
            if "JSON.stringify(window.__probe" in script:
                return json.dumps({"ok": True, "steps": ["aviso"], "placeholder_shown": True,
                                   "sentinel_in_result": False})
            assert json.dumps(SENTINEL.split()[-1]) in script  # el JS recibe el token a buscar
            return None

        def destroy(self):
            pass

    def fake_run_window(config, on_loaded=None):
        profile = appdata.webview_profile_dir()
        profile.mkdir(parents=True)
        try:
            on_loaded(Window(), Api())
        finally:
            appdata.cleanup_webview_profile(profile)

    monkeypatch.setattr(main, "run_window", fake_run_window)
    out = tmp_path / "sonda"
    code = privacy_probe.run(main.parse_args([]), out, SENTINEL, hold=0)
    report_raw = (out / "probe-report.json").read_text(encoding="utf-8")
    report = json.loads(report_raw)
    assert SENTINEL.split()[-1] not in report_raw  # el informe nunca contiene el centinela
    assert code == 0, report
    assert report["checks"]["exports_anonymized"] and report["checks"]["profile_removed_on_close"]
    assert {p.name for p in (out / "export").iterdir()} == {"resultado.md", "resultado.txt",
                                                           "resultado.docx", "resultado.json"}
    if report["ocr_engines"]:
        assert report["ocr"]["statuses"] == ["done", "done"] and report["ocr"]["in_worker_processes"]
        assert report["ocr"]["sentinel_read_by_ocr"]  # el OCR leyó el centinela... y no salió en el resultado
        assert report["checks"]["ocr_output_anonymized"]


def test_probe_requires_full_sentinel():
    with pytest.raises(SystemExit):
        main.parse_args(["--privacy-probe", "x", "--probe-sentinel", "Solo"])
    cfg = main.parse_args(["--privacy-probe", "x", "--probe-sentinel", SENTINEL, "--probe-crash"])
    assert cfg.privacy_probe == Path("x") and cfg.probe_crash
