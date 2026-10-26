# Tool Tự Động Tải XML Hóa Đơn Từ Cổng Thuế

Ứng dụng Desktop tự động hóa quy trình tải hóa đơn điện tử mua vào từ cổng Tổng cục Thuế (`hoadondientu.gdt.gov.vn`), trích xuất chính xác file `invoice.xml` vào thư mục `ALLINVOICE/`, và tự động xuất dữ liệu ra file Excel phục vụ bước đối chiếu kế toán / iPOS.

---

## 1. Tính năng nổi bật

- **Phiên đăng nhập bền vững (Persistent Session)**: Sử dụng Chromium Playwright với thư mục hồ sơ riêng (`browser_profile/`) để lưu trữ cookie và session. Người dùng tự đăng nhập và xác thực CAPTCHA một lần, các lần sau không cần đăng nhập lại khi phiên còn hiệu lực.
- **An toàn & Bảo mật tuyệt đối**: Không lưu mật khẩu cổng Thuế trong mã nguồn hay cấu hình. Người dùng tự chủ động đăng nhập.
- **Tự động mở và tải từng hóa đơn**: Tự động duyệt từng dòng hóa đơn trong bảng Ant Design, click mở chi tiết trước khi kích hoạt lệnh tải.
- **Trích xuất XML thông minh từ ZIP**:
  - Đọc file ZIP trực tiếp trong bộ nhớ.
  - **Chỉ trích xuất file `invoice.xml`** lưu vào thư mục `ALLINVOICE/`.
  - Bỏ qua hoàn toàn các file `details.js`, `invoice.html` và file ảnh `.jpg`.
- **Đặt tên file XML chuẩn hóa**:
  - Cấu trúc: `{MST_NGUOI_BAN}_{KY_HIEU}_{SO_HOA_DON}_{NGAY_LAP}.xml`
  - Ví dụ: `3400401523_C26TNT_00005286_20261009.xml`
  - Giữ nguyên toàn bộ số 0 ở đầu của số hóa đơn (`SHDon`).
- **Lưu trữ tiến độ với SQLite**: Tránh tải trùng lặp các hóa đơn đã có, cho phép dừng và tiếp tục mượt mà.
- **Xuất báo cáo Excel chuyên nghiệp (`output/tax_invoices.xlsx`)** gồm 4 sheet:
  1. `HoaDon`: Thông tin tổng quan từng hóa đơn (MST người bán/mua, số HĐ, tiền trước thuế, thuế, tổng thanh toán, tên file XML).
  2. `ChiTietSanPham`: Từng dòng hàng hóa dịch vụ (mã hàng, tên hàng, ĐVT, số lượng, đơn giá, thành tiền, thuế suất, tiền thuế dòng hàng, file XML nguồn).
  3. `LichSuTai`: Nhật ký quá trình tải, trạng thái, mã lỗi (nếu có).
  4. `ThongKe`: Thống kê tổng quan số hóa đơn tìm thấy, thành công, bỏ qua và lỗi.

---

## 2. Hướng dẫn khởi chạy nhanh

### Cách 1: Khởi chạy bằng file BAT (Khuyến nghị cho Windows)
Chỉ cần nhấp đúp vào file:
```cmd
run_tool.bat
```
File này sẽ tự động kiểm tra thư viện Python, cài đặt Playwright Chromium và mở giao diện ứng dụng.

### Cách 2: Khởi chạy bằng lệnh Python
```bash
# 1. Cài đặt thư viện
pip install -r requirements.txt

# 2. Cài đặt trình duyệt Playwright Chromium
python -m playwright install chromium

# 3. Chạy ứng dụng
python main.py
```

---

## 3. Quy trình sử dụng trên giao diện

1. **Bước 1: Mở Cổng Thuế & Đăng nhập**:
   - Bấm nút **"🌐 1. Mở Cổng Thuế"** trên giao diện tool.
   - Cửa sổ trình duyệt Chromium sẽ mở ra trang web Cổng Thuế.
   - Đăng nhập tài khoản của bạn và hoàn thành mã CAPTCHA.
   - Bấm **"🔍 Kiểm tra Phiên"** trên tool để xác nhận trạng thái.

2. **Bước 2: Thiết lập Bộ lọc tra cứu**:
   - Nhập khoảng thời gian: **Từ ngày** - **Đến ngày** (định dạng `dd/mm/yyyy`).
   - Tùy chỉnh thời gian chờ giữa các lần tải (mặc định 1.0 giây để bảo vệ server).

3. **Bước 3: Bắt đầu tải**:
   - Bấm **"🚀 2. Bắt đầu tải XML hóa đơn"**.
   - Tool sẽ tự động chuyển đến tab Hóa đơn mua vào, thiết lập bộ lọc, tìm kiếm, duyệt qua từng dòng và từng trang để tải hóa đơn.
   - Tiến độ và danh sách hóa đơn sẽ cập nhật trực tiếp trên bảng.

4. **Bước 4: Xuất Excel & Kiểm tra kết quả**:
   - Bấm **"📊 Xuất Excel Tổng Hợp"** để tạo file báo cáo `output/tax_invoices.xlsx`.
   - Bấm **"📁 Mở Thư Mục ALLINVOICE"** để xem toàn bộ các file `.xml` đã được trích xuất.
   - Bấm **"📄 Mở File Excel"** để mở trực tiếp file báo cáo.

---

## 4. Cấu trúc thư mục dự án

```text
D:\TOOLINVOICE\
├── main.py                     # File chạy chính
├── run_tool.bat                # Phím tắt khởi chạy trên Windows
├── requirements.txt            # Thư viện phụ thuộc
├── README.md                   # Hướng dẫn sử dụng
├── ALLINVOICE/                 # Thư mục lưu trữ XML hóa đơn chuẩn hóa
├── downloads/                  # Thư mục tạm khi tải file ZIP
├── logs/                       # File log app.log và cơ sở dữ liệu manifest.db
├── output/                     # Thư mục chứa báo cáo tax_invoices.xlsx
├── browser_profile/            # Dữ liệu phiên duyệt web Playwright
├── docs/
│   └── SPEC.md                 # Tài liệu đặc tả kỹ thuật chi tiết
├── src/
│   └── tax_invoice_downloader/
│       ├── __init__.py         # Package entry
│       ├── app.py              # Giao diện Desktop Tkinter
│       ├── browser_session.py  # Quản lý trình duyệt persistent session
│       ├── tax_portal.py       # Tự động hóa thao tác cổng Thuế
│       ├── download_manager.py # Quản lý tải, trích xuất XML và lưu manifest
│       ├── zip_xml_extractor.py# Trích xuất invoice.xml an toàn trong RAM
│       ├── xml_parser.py       # Phân tích cú pháp XML Hóa đơn TT78/NĐ123
│       ├── excel_exporter.py   # Xuất Excel 4 sheet theo chuẩn
│       ├── models.py           # Định nghĩa cấu trúc dữ liệu Data Class
│       └── logging_config.py   # Cấu hình log và SQLite Manifest DB
└── tests/
    ├── test_zip_xml_extractor.py
    ├── test_xml_parser.py
    ├── test_excel_exporter.py
    └── test_download_manager.py
```

---

## 5. Chạy Kiểm Thử (Unit Tests)

Để kiểm tra toàn bộ các thành phần hệ thống:
```bash
python -m unittest discover tests
```
Tất cả 14 bài kiểm thử về trích xuất ZIP, phân tích cú pháp XML, tạo báo cáo Excel và quản lý tải xuống đều vượt qua kiểm tra thành công.
