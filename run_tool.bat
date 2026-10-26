@echo off
cd /d "%~dp0"
title Tax Invoice Downloader

echo ========================================================
echo   TOOL TU DONG TAI XML HOA DON TU CONG THUE
echo ========================================================
echo.

python -c "import playwright, openpyxl, lxml" >nul 2>nul
if errorlevel 1 (
    echo Dang cai dat thu vien can thiet, vui long doi...
    python -m pip install -r requirements.txt
    python -m playwright install chromium
)

echo Dang mo giao dien Tool...
python main.py
if errorlevel 1 (
    echo.
    echo Ung dung da dong voi ma loi.
    pause
)
