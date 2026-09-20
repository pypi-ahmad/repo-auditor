@echo off
setlocal
cd /d "%~dp0"
set "STREAMLIT_PORT=8594"

if not exist ".env" (
    copy ".env.example" ".env" >nul
    start "" /wait notepad.exe ".env"
    exit /b 0
)

if not exist ".venv" (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
)

.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 exit /b 1

set "STOPPED_LISTENER="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%STREAMLIT_PORT% .*LISTENING"') do (
    echo Stopping the existing listener on port %STREAMLIT_PORT% (PID %%P)...
    taskkill /PID %%P /F >nul 2>&1
    set "STOPPED_LISTENER=1"
)

if defined STOPPED_LISTENER timeout /t 1 /nobreak >nul

echo Starting Repo Auditor at http://localhost:%STREAMLIT_PORT%
.venv\Scripts\streamlit run app.py --server.port %STREAMLIT_PORT%
