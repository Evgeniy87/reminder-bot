@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.11+
    pause
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting Reminder Bot...
echo Press Ctrl+C to stop.
echo.
python bot.py

pause
