@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Tax Invoice Downloader - Tự động tải XML Hóa Đơn Thuế

echo ========================================================
echo   CÔNG CỤ TỰ ĐỘNG TẢI XML HÓA ĐƠN TỪ CỔNG THUẾ
echo ========================================================
echo.

echo [1/3] Đang kiểm tra thư viện Python...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LỖI] Không thể cài đặt các thư viện cần thiết.
    echo Vui lòng kiểm tra Python và kết nối mạng Internet.
    pause
    exit /b 1
)

echo.
echo [2/3] Đang kiểm tra trình duyệt Chromium Playwright...
python -m playwright install chromium
if errorlevel 1 (
    echo [CẢNH BÁO] Không thể tự động cài Playwright Chromium. Tiếp tục khởi động...
)

echo.
echo [3/3] Đang khởi chạy giao diện ứng dụng...
python main.py
if errorlevel 1 (
    echo.
    echo Ứng dụng đã đóng với mã lỗi.
    pause
)
