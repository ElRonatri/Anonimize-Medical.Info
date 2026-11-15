@echo off
REM Ejecuta la aplicacion desde el codigo fuente (requiere haber compilado frontend\dist).
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
if not exist frontend\dist\index.html (pushd frontend & call npm install & call npm run build & popd)
python backend\main.py
endlocal
