# -*- mode: python ; coding: utf-8 -*-
# Especificación de PyInstaller para generar el ejecutable de Windows.
#   Uso:  pyinstaller --noconfirm --clean anonimize.spec
#   Requiere haber compilado antes la interfaz: cd frontend && npm run build

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, copy_metadata

ROOT = Path(SPECPATH)
DIST_UI = ROOT / "frontend" / "dist"
if not (DIST_UI / "index.html").exists():
    raise SystemExit("Falta frontend/dist. Ejecuta: cd frontend && npm install && npm run build")

# ------------------------------------------------------------------ versión
# Fuente única: backend/anonymizer/__init__.py (__version__). Se lee sin importar el paquete.
import re

_init = (ROOT / "backend" / "anonymizer" / "__init__.py").read_text(encoding="utf-8")
APP_VERSION = re.search(r'^__version__ = "([^"]+)"', _init, re.M).group(1)
_nums = [int(x) for x in re.findall(r"\d+", APP_VERSION)[:4]]
_nums += [0] * (4 - len(_nums))
VERSION_FILE = Path(workpath) / "version_info.txt"
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(_nums)}, prodvers={tuple(_nums)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040A04B0', [
      StringStruct('CompanyName', 'Anonimize Medical'),
      StringStruct('FileDescription', 'Anonimize Medical - anonimización local de documentos médicos'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', 'AnonimizeMedical'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'AnonimizeMedical.exe'),
      StringStruct('ProductName', 'Anonimize Medical'),
      StringStruct('ProductVersion', '{APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x040A, 1200])])
  ]
)
""", encoding="utf-8")
print(f"Anonimize Medical {APP_VERSION}")

datas = [(str(DIST_UI), "web")]
datas += collect_data_files("webview")
datas += collect_data_files("docx")  # plantillas de python-docx (default.docx, estilos)
# Léxico clínico del NER (texto, se incluye siempre: es pequeño y editable)
datas.append((str(ROOT / "backend" / "anonymizer" / "data"), "anonymizer/data"))
binaries = collect_dynamic_libs("pypdfium2_raw")

hiddenimports = ["pdfplumber", "pdfminer", "pypdfium2", "pyperclip", "docx", "ahocorasick"]

# Tesseract empaquetado (build.bat --tesseract): copia la instalación local a "tesseract/".
import os

tesseract_dir = os.environ.get("BUNDLE_TESSERACT_DIR")
if tesseract_dir:
    tess = Path(tesseract_dir)
    if not (tess / "tesseract.exe").is_file():
        raise SystemExit(f"No se encontró tesseract.exe en {tess}")
    datas.append((str(tess), "tesseract"))

# ------------------------------------------------------------------ variantes de build
# Regla: todo motor que aumente el tamaño del ejecutable es OPCIONAL y se activa explícitamente.
#   (base)                     sin motores OCR empaquetados; usa Tesseract si está instalado
#   BUNDLE_RAPIDOCR=1          + RapidOCR con sus modelos ONNX   (build.bat --ocr)
#   BUNDLE_TESSERACT_DIR=...   + Tesseract portable              (build.bat --tesseract)
# Nunca se descarga nada en tiempo de ejecución: los modelos van dentro del paquete.
excludes = ["tkinter", "matplotlib", "pytest", "reportlab"]
variant = ["base"]

if os.environ.get("BUNDLE_RAPIDOCR") == "1":
    import rapidocr  # falla el build si se pidió la variante y no está instalado

    datas += collect_data_files("rapidocr")  # incluye los modelos .onnx
    binaries += collect_dynamic_libs("onnxruntime")
    hiddenimports += ["rapidocr", "onnxruntime", "numpy"]
    variant.append("rapidocr")
else:
    excludes += ["rapidocr", "onnxruntime"]  # aunque estén instalados en el entorno

NER_PACKAGES = ["spacy", "thinc", "xx_ent_wiki_sm", "es_core_news_sm", "en_core_web_sm"]
if os.environ.get("BUNDLE_NER") == "1":
    import spacy  # noqa: F401  # falla el build si se pidió la variante y no está instalado

    # spaCy registra arquitecturas y modelos por entry points y lee metadatos de paquetes:
    # se incluyen completos (código, datos, binarios y metadatos).
    for package in ("spacy", "thinc", "srsly", "blis", "cymem", "preshed", "murmurhash",
                    "catalogue", "confection", "wasabi", "weasel", "langcodes", "xx_ent_wiki_sm"):
        try:
            pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        except Exception:  # paquete opcional no instalado
            continue
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    for package in ("spacy", "thinc", "xx_ent_wiki_sm", "catalogue", "confection"):
        datas += copy_metadata(package)
    variant.append("ner")
else:
    excludes += NER_PACKAGES  # aunque estén instalados en el entorno

if tesseract_dir:
    variant.append("tesseract")

print(f"Variante: {' + '.join(variant)}")

a = Analysis(
    [str(ROOT / "backend" / "main.py")],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
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
    version=str(VERSION_FILE),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="AnonimizeMedical", upx=False)
