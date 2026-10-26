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
echo Python: %PY_CMD%
echo.

echo [1/3] Đang kiểm tra thư viện Python...
"%PY_CMD%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LỖI] Không thể cài đặt các thư viện cần thiết.
    pause
    exit /b 1
)

echo.
echo [2/3] Đang kiểm tra trình duyệt Chromium Playwright...
"%PY_CMD%" -m playwright install chromium

echo.
echo [3/3] Đang khởi chạy giao diện ứng dụng...
"%PY_CMD%" main.py
if errorlevel 1 (
    echo.
    echo Ứng dụng đã đóng với mã lỗi.
    pause
)
