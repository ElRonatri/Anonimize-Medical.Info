# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para generar el ejecutable de Windows.
#   Uso:  pyinstaller --noconfirm --clean anonimize.spec
#   Requiere haber compilado antes la interfaz: cd frontend && npm run build

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH)
DIST_UI = ROOT / "frontend" / "dist"
if not (DIST_UI / "index.html").exists():
    raise SystemExit("Falta frontend/dist. Ejecuta: cd frontend && npm install && npm run build")

datas = [(str(DIST_UI), "web")]
datas += collect_data_files("webview")
datas += collect_data_files("docx")  # plantillas de python-docx (default.docx, estilos)
binaries = collect_dynamic_libs("pypdfium2_raw")

hiddenimports = ["pdfplumber", "pdfminer", "pypdfium2", "pyperclip", "docx", "pytesseract"]

# Tesseract empaquetado (build.bat --tesseract): copia la instalación local a "tesseract/".
import os

tesseract_dir = os.environ.get("BUNDLE_TESSERACT_DIR")
if tesseract_dir:
    tess = Path(tesseract_dir)
    if not (tess / "tesseract.exe").is_file():
        raise SystemExit(f"No se encontró tesseract.exe en {tess}")
    datas.append((str(tess), "tesseract"))

# OCR opcional: se incluye sólo si está instalado (pip install -r requirements-ocr.txt)
try:
    import rapidocr  # noqa: F401

    datas += collect_data_files("rapidocr")
    binaries += collect_dynamic_libs("onnxruntime")
    hiddenimports += ["rapidocr", "onnxruntime", "numpy"]
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "backend" / "main.py")],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "reportlab"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnonimizeMedical",
    icon=str(ROOT / "assets" / "icon.ico"),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="AnonimizeMedical", upx=False)
