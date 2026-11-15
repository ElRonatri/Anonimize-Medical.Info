@echo off
REM Modo desarrollo: Vite con recarga en caliente + ventana PyWebView con DevTools.
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
if not exist frontend\node_modules (pushd frontend & call npm install & popd)
start "Vite" cmd /c "cd frontend && npm run dev"
timeout /t 3 /nobreak >nul
python backend\main.py --dev
endlocal
