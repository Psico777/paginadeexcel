@echo off
echo ==========================================
echo   EMFOX OMS - Iniciando Sistema
echo ==========================================
echo.

echo [1/2] Iniciando Backend (FastAPI)...
cd /d "%~dp0backend"
start "EMFOX-Backend" cmd /k "python -m uvicorn app.main:app --reload --port 8000"

echo [2/2] Iniciando Frontend (React + Vite)...
cd /d "%~dp0frontend"
start "EMFOX-Frontend" cmd /k "npm run dev"

echo.
echo ==========================================
echo   Sistema iniciado!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo ==========================================
pause
