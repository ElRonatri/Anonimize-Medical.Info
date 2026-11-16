@echo off
REM Compila la interfaz y genera el ejecutable de Windows en dist\AnonimizeMedical\
REM Uso:  build.bat [--ocr] [--tesseract] [--ner]
REM   --ocr        incluye el motor OCR RapidOCR (~100 MB, no requiere instalar nada mas)
REM   --ner        incluye la deteccion adicional de nombres (spaCy + modelo multilingue, MIT)
REM   --tesseract  copia Tesseract instalado en el equipo dentro del ejecutable
REM                (por defecto desde "C:\Program Files\Tesseract-OCR"; cambiar con TESSERACT_DIR)
setlocal
cd /d "%~dp0"

set WITH_OCR=0
set WITH_TESS=0
set WITH_NER=0
:args
if "%~1"=="" goto args_done
if /I "%~1"=="--ocr" set WITH_OCR=1
if /I "%~1"=="--tesseract" set WITH_TESS=1
if /I "%~1"=="--ner" set WITH_NER=1
shift
goto args
:args_done

where python >nul 2>nul || (echo [ERROR] No se encontro Python 3.10+ en el PATH. & exit /b 1)
where npm >nul 2>nul || (echo [ERROR] No se encontro Node.js/npm en el PATH. & exit /b 1)

if not exist .venv (
  echo Creando entorno virtual...
  python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat || exit /b 1

echo Instalando dependencias de Python...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || exit /b 1
if "%WITH_OCR%"=="1" pip install -r requirements-ocr.txt || exit /b 1
set BUNDLE_RAPIDOCR=
if "%WITH_OCR%"=="1" set BUNDLE_RAPIDOCR=1
if "%WITH_NER%"=="1" pip install -r requirements-ner.txt || exit /b 1
set BUNDLE_NER=
if "%WITH_NER%"=="1" set BUNDLE_NER=1

set BUNDLE_TESSERACT_DIR=
if "%WITH_TESS%"=="1" (
  if "%TESSERACT_DIR%"=="" set "TESSERACT_DIR=C:\Program Files\Tesseract-OCR"
  call set "BUNDLE_TESSERACT_DIR=%%TESSERACT_DIR%%"
)
if "%WITH_TESS%"=="1" if not exist "%BUNDLE_TESSERACT_DIR%\tesseract.exe" (
  echo [ERROR] No se encontro tesseract.exe en "%BUNDLE_TESSERACT_DIR%".
  echo Instala Tesseract desde https://github.com/UB-Mannheim/tesseract/wiki o define TESSERACT_DIR.
  exit /b 1
)

echo Compilando interfaz (React + Tailwind)...
pushd frontend
if exist package-lock.json (call npm ci) else (call npm install)
if errorlevel 1 (popd & exit /b 1)
call npm run build
if errorlevel 1 (popd & exit /b 1)
popd

echo Generando ejecutable...
pyinstaller --noconfirm --clean anonimize.spec || exit /b 1

echo.
echo Listo: dist\AnonimizeMedical\AnonimizeMedical.exe
endlocal
