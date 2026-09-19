@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [.env] File created from .env.example. Opening in Notepad...
        start /wait notepad .env
        echo Please review .env and re-run run.cmd.
        exit /b 0
    )
)

if not exist ".venv" (
    echo [.venv] Creating virtual environment with py -3...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo [WARN] py -3 failed, falling back to python...
        python -m venv .venv
    )
)

call .venv\Scripts\activate.bat
echo [pip] Installing requirements...
pip install -r requirements.txt

echo [streamlit] Starting Streamlit app...
streamlit run app.py
