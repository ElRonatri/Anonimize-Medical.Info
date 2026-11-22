"""Sonda de privacidad en disco: usa la aplicación real con un dato centinela sintético.

Uso (CI de Windows, ejecutable congelado)::

    AnonimizeMedical.exe --privacy-probe <carpeta> --probe-sentinel "Zxqwerty Centinela <azar>"

Abre la ventana real (WebView2), y desde un hilo:

1. maneja la interfaz con JavaScript: acepta el aviso, pega un texto clínico sintético con el
   centinela como nombre del paciente, lo anonimiza y copia el resultado;
2. procesa un PDF escaneado sintético (imagen con el centinela) por OCR en procesos paralelos;
3. exporta los resultados (md, txt, docx, json) a ``<carpeta>/export``, como «Guardar como»;
4. cierra la ventana (o, con ``--probe-crash``, termina el proceso de golpe para simular un fallo).

Escribe ``<carpeta>/probe-report.json`` **sin el centinela**: sólo booleanos, rutas y nombres de
archivos. La búsqueda del centinela en ``%TEMP%``, ``%LOCALAPPDATA%``, ``%APPDATA%`` y el perfil
de WebView2 la hace el CI después de cerrar la aplicación (``scripts/scan_residue.ps1``).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROBE_TEXT = (
    "EPICRISIS\n"
    "Paciente: {sentinel}\n"
    "RUT: 12.345.678-5\n"
    "Fecha de nacimiento: 21/08/1985\n"
    "Diagnóstico: Neumonía adquirida en la comunidad.\n"
    "Se conversó con la paciente Sra. {last} sobre el control.\n"
)

# JavaScript que maneja la interfaz real. Resultado en window.__probe (sin el centinela).
UI_SCRIPT = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (fn, ms = 30000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) { const v = fn(); if (v) return v; await sleep(100); }
    throw new Error('timeout');
  };
  const steps = [];
  try {
    const ok = await until(() => document.querySelector('[data-testid=responsible-ok]'));
    ok.click(); steps.push('aviso');
    document.querySelector('[data-testid=theme-toggle]')?.click(); steps.push('tema');
    (await until(() => document.querySelector('[data-testid=option-paste]'))).click();
    const ta = await until(() => document.querySelector('[data-testid=paste-text]'));
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    setter.call(ta, __TEXT__);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    const ready = () => {
      const b = document.querySelector('[data-testid=anonymize-text]');
      return b && !b.disabled && b;
    };
    (await until(ready)).click();
    steps.push('anonimizar');
    const copy = await until(() => document.querySelector('[data-testid=copy-result]'));
    await sleep(300);
    const shown = document.body.innerText;
    copy.click(); steps.push('copiar');
    await sleep(500);
    window.__probe = { ok: true, steps, placeholder_shown: shown.includes('[PACIENTE'),
                       sentinel_in_result: shown.includes(__TOKEN__) };
  } catch (e) {
    window.__probe = { ok: false, steps, error: String(e && e.message || e) };
  }
})();
"""


def _scanned_pdf(sentinel: str) -> bytes:
    """PDF escaneado sintético (sólo imagen, sin capa de texto) con el centinela."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=56)
    draw.text((60, 80), "EPICRISIS", fill="black", font=font)
    draw.text((60, 220), f"Paciente: {sentinel}", fill="black", font=font)
    draw.text((60, 360), "Hemoglobina 13.1 g/dL", fill="black", font=font)
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=150)
    return out.getvalue()


def _contains(data: bytes, token: str) -> bool:
    return any(enc in data for enc in (token.encode("utf-8"), token.encode("utf-16-le")))


def _export_contains(data: bytes, fmt: str, token: str) -> bool:
    if fmt == "docx":  # zip: revisar cada parte descomprimida
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return any(_contains(zf.read(name), token) for name in zf.namelist())
    return _contains(data, token)


def _profile_snapshot(profile: Path) -> dict[str, Any]:
    if not profile.exists():
        return {"exists": False}
    entries = sorted(p.relative_to(profile).as_posix() for p in profile.rglob("*"))
    return {
        "exists": True,
        "files": len(entries),
        "crashpad": any("Crashpad" in e for e in entries),
        "local_storage": any("Local Storage" in e for e in entries),
        "top_level": sorted({e.split("/")[0] for e in entries})[:40],
    }


def run(config: Any, out_dir: Path, sentinel: str, run_window: Callable[..., None],
        crash: bool = False, hold: float = 5.0, deadline: float = 600.0) -> int:
    import appdata
    from anonymizer import ocr
    from anonymizer.exporters import FORMATS, export_bytes
    from anonymizer.privacy import log_exception

    out_dir.mkdir(parents=True, exist_ok=True)
    token = sentinel.split()[-1]  # parte aleatoria: única en el disco
    profile = appdata.webview_profile_dir()
    report: dict[str, Any] = {"profile_dir": str(profile), "prefs_file": str(appdata.prefs_path()),
                              "crash_simulated": crash, "checks": {}}
    checks: dict[str, bool] = report["checks"]
    report["stage"] = "esperando la ventana"

    # Plazo máximo: si algo se cuelga (la ventana no carga, WebView2 no responde), la sonda
    # termina con un informe que dice en qué etapa quedó, en lugar de bloquear el CI.
    def expire() -> None:
        report["error"] = f"plazo de {deadline:.0f} s agotado en la etapa: {report['stage']}"
        _write(out_dir, report)
        os._exit(4)

    watchdog = threading.Timer(deadline, expire)
    watchdog.daemon = True
    watchdog.start()

    def drive(window: Any, api: Any) -> None:
        try:
            text = PROBE_TEXT.format(sentinel=sentinel, last=sentinel.split()[-2])
            script = UI_SCRIPT.replace("__TEXT__", json.dumps(text)).replace("__TOKEN__", json.dumps(token))
            report["stage"] = "interfaz (texto pegado)"
            window.evaluate_js(script)
            deadline = time.monotonic() + 90
            ui: Any = None
            while time.monotonic() < deadline and not ui:
                time.sleep(0.25)
                ui = json.loads(window.evaluate_js("JSON.stringify(window.__probe || null)") or "null")
            report["ui"] = ui
            checks["ui_flow"] = bool(ui and ui.get("ok") and ui.get("placeholder_shown"))
            checks["ui_result_anonymized"] = bool(ui and ui.get("ok") and not ui.get("sentinel_in_result"))

            # PDF escaneado por OCR, en procesos paralelos (spawn), igual que un lote real.
            report["stage"] = "OCR en procesos paralelos"
            engines = ocr.available_engines()
            report["ocr_engines"] = engines
            pdf = base64.b64encode(_scanned_pdf(sentinel)).decode()
            files = [{"name": f"escaneo_sintetico_{n}.pdf", "data": pdf} for n in (1, 2)]  # 2 = en paralelo
            job = api.start_batch(files, {"ocr_mode": "force", "parallel": "force", "max_workers": 2,
                                          "output_format": "markdown"})
            state = api.get_job(job["job_id"])
            end = time.monotonic() + 300
            while not state["done"] and time.monotonic() < end:
                time.sleep(0.2)
                state = api.get_job(job["job_id"])
            results = list(state.get("results", {}).values())
            items = state.get("items", [])
            docs = [api._items[i["id"]].doc for i in items if i["id"] in api._items]
            raw = " ".join(d.full_text() for d in docs if d is not None)
            report["ocr"] = {"statuses": [i.get("status") for i in items],
                             "in_worker_processes": bool(items) and all(i.get("worker") not in (None, os.getpid())
                                                                        for i in items),
                             "sentinel_read_by_ocr": token.lower() in raw.lower()}
            outputs = [r["text"] for r in results if r.get("ok")]
            checks["ocr_output_anonymized"] = all(token not in t for t in outputs)

            # Exportación (lo que haría «Guardar como»), con el resultado del texto pegado.
            report["stage"] = "exportación"
            pasted = api.process_text(text, {"output_format": "markdown"})
            export_dir = out_dir / "export"
            export_dir.mkdir(exist_ok=True)
            leaked = []
            for fmt in FORMATS:
                data = export_bytes(fmt, pasted["result"]["text"], pasted["result"])
                (export_dir / f"resultado.{fmt}").write_bytes(data)
                if _export_contains(data, fmt, token):
                    leaked.append(fmt)
            report["export_formats"] = list(FORMATS)
            checks["exports_anonymized"] = not leaked

            report["profile_during_run"] = _profile_snapshot(profile)
            # PDF censurado: uno con capa de texto y los escaneados (si hubo OCR), todos con el centinela.
            report["stage"] = "PDF censurado"
            from anonymizer.redact_pdf import synthetic_text_pdf

            text_pdf = synthetic_text_pdf([f"Paciente: {sentinel}", "RUT: 15.234.567-K",
                                           "Diagnostico: Neumonia adquirida en la comunidad."])
            job = api.start_batch([{"name": "texto_sintetico.pdf", "data": base64.b64encode(text_pdf).decode()}],
                                  {"ocr_mode": "off"})
            state = api.get_job(job["job_id"])
            end = time.monotonic() + 120
            while not state["done"] and time.monotonic() < end:
                time.sleep(0.1)
                state = api.get_job(job["job_id"])
            pdf_items = state["items"] + items
            pdf_reports = []
            for n, pdf_item in enumerate(pdf_items):
                res = api._write_redacted_pdf(export_dir / f"censurado_{n}.pdf", {"id": pdf_item["id"]}, {})
                out = (export_dir / f"censurado_{n}.pdf").read_bytes() if res.get("ok") else b""
                pdf_reports.append({"ok": bool(res.get("ok")), "redactions": res.get("report", {}).get("redactions", 0),
                                    "unlocated": len(res.get("report", {}).get("unlocated", [])),
                                    "sentinel_in_file": _contains(out, token)})
            report["redacted_pdfs"] = pdf_reports
            checks["redacted_pdf_text_layer"] = bool(pdf_reports) and pdf_reports[0]["ok"] \
                and pdf_reports[0]["redactions"] >= 1 and pdf_reports[0]["unlocated"] == 0
            checks["redacted_pdfs_without_sentinel"] = all(r["ok"] and not r["sentinel_in_file"] for r in pdf_reports)
            if report.get("ocr", {}).get("sentinel_read_by_ocr"):
                checks["redacted_pdf_scanned"] = all(r["redactions"] >= 1 for r in pdf_reports[1:])

            report["stage"] = "ventana abierta (muestreo del CI)"
            time.sleep(hold)  # el CI inspecciona los procesos de WebView2 mientras tanto
        except Exception as exc:  # el informe debe escribirse igual
            report["error"] = type(exc).__name__
            log_exception(log, "Sonda de privacidad", exc)
        finally:
            _write(out_dir, report)
            if crash:
                os._exit(3)  # cierre abrupto: sin limpieza (prueba la limpieza al iniciar)
            window.destroy()

    run_window(config, on_loaded=drive)
    report["stage"] = "cerrada"
    watchdog.cancel()
    time.sleep(1.0)
    report["webview2"] = {k: v for k, v in appdata.WEBVIEW2_STATUS.items() if k != "hooked_class"}
    report["webview2"]["args"] = list(appdata.WEBVIEW2_ARGS)
    report["profile_after_close"] = _profile_snapshot(profile)
    checks["profile_removed_on_close"] = not profile.exists()
    prefs = appdata.prefs_path()
    report["prefs_keys"] = sorted(appdata.PrefStore(prefs).load()) if prefs.exists() else []
    checks["prefs_without_sentinel"] = not (prefs.exists() and _contains(prefs.read_bytes(), token))
    report["ok"] = all(checks.values()) and "error" not in report
    _write(out_dir, report)
    return 0 if report["ok"] else 1


def _write(out_dir: Path, report: dict[str, Any]) -> None:
    (out_dir / "probe-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
