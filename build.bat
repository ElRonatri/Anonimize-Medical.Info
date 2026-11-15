@echo off
REM Compila la interfaz y genera el ejecutable de Windows en dist\AnonimizeMedical\
setlocal
cd /d "%~dp0"

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
if /I "%1"=="--ocr" pip install -r requirements-ocr.txt || exit /b 1

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
