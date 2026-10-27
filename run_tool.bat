@echo off
cd /d "%~dp0"
title Tool Tu Dong Tai XML Hoa Don Tu Cong Thue

echo ========================================================
echo   TOOL TU DONG TAI XML HOA DON TU CONG THUE
echo ========================================================
echo.

set "PY_CMD="

:: 1. Kiem tra py launcher
py -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py"
    goto :found_python
)

:: 2. Kiem tra python trong LocalAppData (Python 3.13 / Python 3.12 / Python 3.11)
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :found_python
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found_python
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found_python
)

:: 3. Kiem tra python tren PATH
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :found_python
)

echo [LOI] Khong tim thay Python tren he thong!
echo Vui long cai dat Python hoac them Python vao bien moi truong PATH.
pause
exit /b 1

:found_python
echo Su dung Python: %PY_CMD%
echo.

:: Kiem tra cac thu vien can thiet
"%PY_CMD%" -c "import playwright, openpyxl, lxml, pandas" >nul 2>nul
if errorlevel 1 (
    echo Dang cai dat thu vien can thiet, vui long doi...
    "%PY_CMD%" -m pip install -r requirements.txt
    "%PY_CMD%" -m playwright install chromium
)

echo Dang mo giao dien Tool...
"%PY_CMD%" main.py
if errorlevel 1 (
    echo.
    echo Ung dung da dong voi ma loi.
    pause
)
