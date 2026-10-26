@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tax Invoice Downloader - Tự động tải XML Hóa Đơn Thuế

set "PY_CMD=python"
if exist "C:\Users\user\AppData\Local\Python\pythoncore-3.15-64\python.exe" (
    set "PY_CMD=C:\Users\user\AppData\Local\Python\pythoncore-3.15-64\python.exe"
) else if exist "C:\Users\user\AppData\Local\Python\bin\python.exe" (
    set "PY_CMD=C:\Users\user\AppData\Local\Python\bin\python.exe"
)

echo ========================================================
echo   CÔNG CỤ TỰ ĐỘNG TẢI XML HÓA ĐƠN TỪ CỔNG THUẾ
echo ========================================================

:: Kiểm tra nếu chưa cài thư viện thì mới tiến hành cài đặt
"%PY_CMD%" -c "import playwright, openpyxl, lxml" >nul 2>nul
if errorlevel 1 (
    echo [Thong bao] Dang cai dat thu vien can thiet, vui long doi trong giay lat...
    "%PY_CMD%" -m pip install -r requirements.txt
    "%PY_CMD%" -m playwright install chromium
)

echo [Khoi dong] Dang mo giao dien Tool...
"%PY_CMD%" main.py
if errorlevel 1 (
    echo.
    echo Da xay ra loi khi chay ung dung.
    pause
)
