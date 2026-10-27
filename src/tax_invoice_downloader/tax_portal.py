"""Tax portal interaction automation: navigating search, selecting invoice rows, triggering downloads, and handling pagination."""

import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from .models import InvoiceKey, InvoiceHeader, SummaryStats
from .download_manager import DownloadManager, DownloadManagerError
from .logging_config import setup_logger

logger = setup_logger("tax_portal")


class SessionExpiredError(Exception):
    """Raised when portal redirects to login screen or session expires."""
    pass


class TaxPortalAutomation:
    """Automates operations on the General Department of Taxation portal (hoadondientu.gdt.gov.vn)."""

    def __init__(self, download_manager: DownloadManager, polite_delay_seconds: float = 1.0):
        self.download_manager = download_manager
        self.polite_delay_seconds = polite_delay_seconds
        self._stop_requested = False

    def request_stop(self):
        """Signals automation loop to stop safely after current step."""
        self._stop_requested = True

    def check_session(self, page: Page):
        """Verifies session is still active. Raises SessionExpiredError if logged out."""
        url = page.url.lower()
        if "dang-nhap" in url or "login" in url:
            raise SessionExpiredError("Phiên làm việc đã hết hạn. Website đã quay lại trang đăng nhập.")

        # Check if login modal appeared
        try:
            pwd_input = page.locator("input[type='password']").first
            if pwd_input.is_visible(timeout=500):
                # Verify it's not a change password screen
                if page.locator("text=Đăng nhập").first.is_visible(timeout=500):
                    raise SessionExpiredError("Phiên làm việc đã hết hạn hoặc yêu cầu đăng nhập lại.")
        except Exception:
            pass

    def navigate_to_purchase_invoices(self, page: Page):
        """Navigates to: Tra cứu -> Tra cứu hóa đơn -> Tra cứu hóa đơn điện tử mua vào."""
        logger.info("Đang điều hướng theo luồng: Tra cứu -> Tra cứu hóa đơn -> Tra cứu hóa đơn điện tử mua vào...")

        try:
            # 0. Check if already on the active 'mua vào' tab
            active_tab = page.locator(".ant-tabs-tab-active:has-text('mua vào'), [role='tab'][aria-selected='true']:has-text('mua vào')").first
            if active_tab.is_visible(timeout=1000):
                logger.info("Đang ở sẵn giao diện 'Hóa đơn điện tử mua vào'.")
                return
        except Exception:
            pass

        # 1. Step 1: Menu 'Tra cứu'
        try:
            tra_cuu_selectors = [
                ".ant-menu-submenu:has-text('Tra cứu')",
                "li.ant-menu-submenu:has-text('Tra cứu')",
                "span:has-text('Tra cứu')",
                "a:has-text('Tra cứu')",
                "text=Tra cứu",
            ]
            for sel in tra_cuu_selectors:
                el = page.locator(sel).first
                if el.is_visible(timeout=1000):
                    el.hover()
                    time.sleep(0.3)
                    el.click()
                    logger.info("Đã bấm menu 'Tra cứu'.")
                    time.sleep(0.6)
                    break
        except Exception as e:
            logger.debug(f"Bước 1 menu 'Tra cứu': {e}")

        # 2. Step 2: Submenu 'Tra cứu hóa đơn'
        try:
            tra_cuu_hd_selectors = [
                ".ant-menu-item:has-text('Tra cứu hóa đơn')",
                "li.ant-menu-item:has-text('Tra cứu hóa đơn')",
                "a:has-text('Tra cứu hóa đơn')",
                "span:has-text('Tra cứu hóa đơn')",
                "text=Tra cứu hóa đơn",
                "a[href*='tra-cuu-hoa-don']",
            ]
            for sel in tra_cuu_hd_selectors:
                el = page.locator(sel).first
                if el.is_visible(timeout=1500):
                    el.click()
                    logger.info("Đã bấm mục 'Tra cứu hóa đơn'.")
                    time.sleep(1.2)
                    break
        except Exception as e:
            logger.debug(f"Bước 2 submenu 'Tra cứu hóa đơn': {e}")

        # 3. Step 3: Tab 'Tra cứu hóa đơn điện tử mua vào'
        try:
            mua_vao_selectors = [
                ".ant-tabs-tab:has-text('mua vào')",
                "div:has-text('Tra cứu hóa đơn điện tử mua vào')",
                "span:has-text('Tra cứu hóa đơn điện tử mua vào')",
                "button:has-text('Tra cứu hóa đơn điện tử mua vào')",
                "[role='tab']:has-text('mua vào')",
                "text=Tra cứu hóa đơn điện tử mua vào",
                "text=Hóa đơn điện tử mua vào",
                ".ant-tabs-tab:nth-child(2)",
            ]
            for sel in mua_vao_selectors:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    logger.info("Đã chọn tab 'Tra cứu hóa đơn điện tử mua vào'.")
                    time.sleep(1.0)
                    break
        except Exception as e:
            logger.warning(f"Bước 3 chọn tab mua vào: {e}")

    def apply_filters_and_search(self, page: Page, from_date: str = "", to_date: str = ""):
        """Sets date filter inputs and triggers search button."""
        self.check_session(page)
        logger.info(f"Thiết lập bộ lọc: Từ ngày '{from_date}' - Đến ngày '{to_date}'")

        try:
            # Locate date inputs (Ant Design DatePicker)
            # From date
            if from_date:
                from_inputs = page.locator(
                    "input[placeholder*='Từ ngày'], "
                    "input[placeholder*='từ ngày'], "
                    "input[id*='fromDate'], "
                    "input[name*='fromDate']"
                )
                if from_inputs.count() > 0:
                    inp = from_inputs.first
                    inp.click()
                    inp.fill(from_date)
                    inp.press("Enter")
                    time.sleep(0.3)

            # To date
            if to_date:
                to_inputs = page.locator(
                    "input[placeholder*='Đến ngày'], "
                    "input[placeholder*='đến ngày'], "
                    "input[id*='toDate'], "
                    "input[name*='toDate']"
                )
                if to_inputs.count() > 0:
                    inp = to_inputs.first
                    inp.click()
                    inp.fill(to_date)
                    inp.press("Enter")
                    time.sleep(0.3)

            # Click Tìm kiếm button
            search_btn = page.locator(
                "button:has-text('Tìm kiếm'), "
                "button:has-text('Tra cứu'), "
                ".ant-btn-primary:has-text('Tìm kiếm')"
            ).first

            if search_btn.is_visible(timeout=3000):
                search_btn.click()
                logger.info("Đã bấm nút Tìm kiếm.")
            else:
                logger.warning("Không tìm thấy nút Tìm kiếm tiêu chuẩn.")

            # Wait for table to load
            self._wait_for_table_loaded(page)

        except Exception as e:
            logger.error(f"Lỗi khi áp dụng bộ lọc: {e}")
            raise

    def _wait_for_table_loaded(self, page: Page, timeout: int = 15000):
        """Waits for Ant Design table spinning indicator to disappear."""
        try:
            # Wait for loading spin to detach if active
            page.wait_for_selector(".ant-spin-spinning", state="detached", timeout=timeout)
        except Exception:
            pass
        time.sleep(1.0)

    def _get_column_map(self, page: Page) -> Dict[str, int]:
        """Dynamically maps table header titles to column indices."""
        col_map: Dict[str, int] = {}
        try:
            th_loc = page.locator("table thead th, div.ant-table-header th, .ant-table-thead th")
            count = th_loc.count()
            for i in range(count):
                txt = th_loc.nth(i).inner_text().strip().lower()
                if "số hóa đơn" in txt or "số hđ" in txt:
                    col_map["sh_hoa_don"] = i
                elif "mẫu số" in txt:
                    col_map["kh_mau_so"] = i
                elif "ký hiệu" in txt:
                    col_map["kh_hoa_don"] = i
                elif "ngày lập" in txt or "ngày hđ" in txt:
                    col_map["ngay_lap"] = i
                elif "mst người bán" in txt or "mã số thuế người bán" in txt:
                    col_map["mst_nguoi_ban"] = i
                elif "người bán" in txt or "tên người bán" in txt:
                    col_map["thong_tin_nguoi_ban"] = i
                elif "tiền chưa thuế" in txt or "chưa thuế" in txt:
                    col_map["tien_chua_thue"] = i
                elif "tiền thuế" in txt:
                    col_map["tien_thue"] = i
                elif "tổng tiền" in txt or "thanh toán" in txt:
                    col_map["tong_tien"] = i
        except Exception:
            pass
        return col_map

    def extract_row_data(self, row: Locator, col_map: Optional[Dict[str, int]] = None) -> Dict[str, str]:
        """Extracts text from cells in an Ant Design table row with dynamic mapping and regex fallback."""
        cells = row.locator("td")
        cell_count = cells.count()
        cell_texts = [cells.nth(i).inner_text().strip() for i in range(cell_count)]

        data = {
            "stt": "",
            "mst_nguoi_mua": "",
            "kh_mau_so": "",
            "kh_hoa_don": "",
            "sh_hoa_don": "",
            "ngay_lap": "",
            "thong_tin_nguoi_ban": "",
            "mst_nguoi_ban": "",
            "tien_chua_thue": "",
            "tien_thue": "",
            "tong_tien": "",
        }

        # Check if first cell is empty checkbox column
        offset = 1 if (cell_count > 7 and not cell_texts[0]) else 0

        # Exact column layout on Cổng Thuế (Tra cứu hóa đơn mua vào):
        # [0] STT (e.g. 1, 2, 3)
        # [1] Mã số thuế người mua (e.g. 060176009807)
        # [2] Ký hiệu mẫu số (e.g. 1)
        # [3] Ký hiệu hóa đơn (e.g. C26TNT)
        # [4] Số hóa đơn (e.g. 5286)
        # [5] Ngày lập (e.g. 09/10/2026)
        # [6] Thông tin người bán (e.g. MST người bán: 3400401523\nTên người bán: ...)
        if cell_count > offset + 5:
            data["stt"] = cell_texts[offset]
            data["mst_nguoi_mua"] = cell_texts[offset + 1]
            data["kh_mau_so"] = cell_texts[offset + 2]
            data["kh_hoa_don"] = cell_texts[offset + 3]
            data["sh_hoa_don"] = cell_texts[offset + 4].strip()
            data["ngay_lap"] = cell_texts[offset + 5].strip()

        if cell_count > offset + 6:
            data["thong_tin_nguoi_ban"] = cell_texts[offset + 6]
            mst_m = re.search(r"\b\d{10}(?:-\d{3})?\b", cell_texts[offset + 6])
            if mst_m:
                data["mst_nguoi_ban"] = mst_m.group(0)

        # Regex fallback to verify and correct any misaligned columns
        for txt in cell_texts:
            # 1. Date: DD/MM/YYYY
            if "/" in txt:
                d_m = re.search(r"\b\d{2}/\d{2}/\d{4}\b", txt)
                if d_m:
                    data["ngay_lap"] = d_m.group(0)

            # 2. Invoice symbol: e.g. C26TNT, 1C23TYY
            s_m = re.search(r"\b[1-9]?[A-Z]\d{2}[A-Z0-9]{2,4}\b", txt)
            if s_m:
                data["kh_hoa_don"] = s_m.group(0)

            # 3. Seller tax code: 10 or 13-14 digits
            if not data["mst_nguoi_ban"]:
                mst_m = re.search(r"\b\d{10}(?:-\d{3})?\b", txt)
                if mst_m and mst_m.group(0) != data["mst_nguoi_mua"]:
                    data["mst_nguoi_ban"] = mst_m.group(0)

        # Clean invoice number
        if data["sh_hoa_don"]:
            data["sh_hoa_don"] = "".join(c for c in data["sh_hoa_don"] if c.isdigit())

        return data

    def _get_table_rows(self, page: Page) -> Locator:
        """Finds main table rows avoiding duplicates from Ant Design fixed-column sidebars."""
        selectors = [
            "div.ant-table-scroll div.ant-table-body tr.ant-table-row",
            "div.ant-table-body table tbody tr.ant-table-row",
            ".ant-table-fixed-left tbody tr.ant-table-row",
            "div.ant-table-content table tbody tr.ant-table-row",
            ".ant-table-tbody tr.ant-table-row",
            "tr.ant-table-row",
            "table tbody tr:not(.ant-table-placeholder):not(:has(th))",
        ]
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                return loc
        return page.locator("tr.ant-table-row")

    def _get_export_xml_button(self, page: Page) -> Optional[Locator]:
        """Định vị chính xác nút 'Xuất xml' trên thanh công cụ bảng."""
        # 1. Định danh chính xác nhất theo SVG Path do Cổng Thuế định nghĩa
        exact_selectors = [
            "button:has(#Path_53113)",
            "button:has(#Path_53114)",
            "button:has([data-name='Path 53113'])",
            "button:has([data-name='Path 53114'])",
            "button.ButtonAnt__IconButton-sc-p5q16s-1:has(#Path_53113)",
            "button.ButtonAnt__IconButton-sc-p5q16s-1:has(#Path_53114)",
            "button:has(svg path[d*='M10.54,4.4'])",
        ]
        for sel in exact_selectors:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                return btn

        # 2. Định danh theo title hoặc tooltip
        for sel in ["button[title*='Xuất xml']", "button[title*='Xuất XML']"]:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                return btn

        # 3. Nút thứ 4 (ngoài cùng bên phải) trong nhóm icon button của thanh công cụ
        # Thứ tự các nút: [Xem (0)] [In (1)] [Kết xuất Excel (2)] [Xuất XML (3)]
        icon_btns = page.locator("button.ButtonAnt__IconButton-sc-p5q16s-1, .ant-btn-icon-only")
        count = icon_btns.count()
        if count >= 4:
            cand = icon_btns.nth(3)  # Nút thứ 4 là Xuất XML
            if cand.is_visible(timeout=300):
                return cand
        elif count > 0:
            cand = icon_btns.last
            if cand.is_visible(timeout=300):
                return cand

        # 4. Fallback theo text
        for sel in ["button:has-text('Xuất XML')", "button:has-text('Xuất xml')", "button:has-text('Tải XML')"]:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                return btn

        return None

    def _select_table_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        export_btn: Optional[Locator],
    ) -> bool:
        """Kích hoạt chọn dòng hóa đơn cho đến khi nút 'Xuất xml' được enabled."""
        row_key = row.get_attribute("data-row-key") or ""
        sh_hoa_don = row_data.get("sh_hoa_don", "")
        kh_hoa_don = row_data.get("kh_hoa_don", "")

        # 1. Thử click trực tiếp vào ô có chữ nhìn thấy được (Số HĐ hoặc Ký hiệu)
        target_cells = []
        if sh_hoa_don:
            target_cells.append(page.locator(f"tr td:has-text('{sh_hoa_don}')"))
        if kh_hoa_don:
            target_cells.append(page.locator(f"tr td:has-text('{kh_hoa_don}')"))
        target_cells.append(row.locator("td"))

        for cell_locator in target_cells:
            count = cell_locator.count()
            for idx in range(min(count, 5)):
                c = cell_locator.nth(idx)
                try:
                    if c.is_visible(timeout=200) and c.inner_text().strip():
                        c.click(timeout=800)
                        time.sleep(0.25)
                        if export_btn and export_btn.is_enabled():
                            logger.debug(f"Đã chọn thành công dòng qua cell (text='{c.inner_text().strip()}')")
                            return True
                except Exception:
                    pass

        # 2. Kích hoạt sự kiện native click thông qua JavaScript trên tất cả phần tử của dòng
        try:
            page.evaluate("""({ key, sh }) => {
                let targets = [];
                if (key) {
                    targets = Array.from(document.querySelectorAll(`tr[data-row-key="${key}"]`));
                }
                if (targets.length === 0 && sh) {
                    const rows = document.querySelectorAll('tr.ant-table-row');
                    targets = Array.from(rows).filter(r => r.innerText.includes(sh));
                }
                targets.forEach(tr => {
                    tr.click();
                    tr.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    Array.from(tr.children).forEach(td => {
                        td.click();
                        td.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    });
                });
            }""", {"key": row_key, "sh": sh_hoa_don})
            time.sleep(0.3)
            if export_btn and export_btn.is_enabled():
                logger.debug(f"Đã chọn thành công dòng qua JavaScript dispatch (key={row_key})")
                return True
        except Exception as e:
            logger.debug(f"JS row selection: {e}")

        # 3. Thử click bảng fixed-left nếu có
        if row_key:
            try:
                fixed_cells = page.locator(f".ant-table-fixed-left tr[data-row-key='{row_key}'] td")
                for i in range(fixed_cells.count()):
                    fc = fixed_cells.nth(i)
                    if fc.is_visible() and fc.inner_text().strip():
                        fc.click(timeout=600)
                        time.sleep(0.25)
                        if export_btn and export_btn.is_enabled():
                            return True
            except Exception:
                pass

        # 4. Fallback click trực tiếp vào dòng
        try:
            row.click(force=True)
            time.sleep(0.25)
            if export_btn and export_btn.is_enabled():
                return True
        except Exception:
            pass

        return False

    def download_invoice_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        retry_limit: int = 2,
    ) -> Optional[InvoiceHeader]:
        """Tải XML một hóa đơn:
        1. Click vào hóa đơn để chọn dòng (hiện highlight dòng).
        2. Chờ nút 'Xuất xml' trên thanh công cụ được kích hoạt (enabled).
        3. Click 'Xuất xml' -> bắt file download -> trích xuất invoice.xml -> lưu ALLINVOICE/.
        4. Tự động hoàn thành để chuyển sang hóa đơn tiếp theo.
        """
        expected_key = InvoiceKey(
            mst_nguoi_ban=row_data.get("mst_nguoi_ban", ""),
            kh_hoa_don=row_data.get("kh_hoa_don", ""),
            sh_hoa_don=row_data.get("sh_hoa_don", ""),
            ngay_lap=row_data.get("ngay_lap", ""),
        )

        logger.info(f"Bắt đầu xử lý hóa đơn: Số={expected_key.sh_hoa_don}, Ký hiệu={expected_key.kh_hoa_don}")

        for attempt in range(retry_limit + 1):
            try:
                # 1. Cuộn đến dòng hóa đơn
                try:
                    row.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                time.sleep(0.1)

                # 2. Tìm nút 'Xuất xml' trên thanh công cụ
                export_btn = self._get_export_xml_button(page)
                if not export_btn:
                    raise DownloadManagerError(
                        f"Không tìm thấy nút 'Xuất xml' trên thanh công cụ cho hóa đơn số {expected_key.sh_hoa_don}"
                    )

                # 3. Kích hoạt chọn dòng hóa đơn cho đến khi nút 'Xuất xml' được kích hoạt
                self._select_table_row(page, row, row_data, export_btn)

                # 4. Chờ thêm tối đa 2s nếu cần để nút 'Xuất xml' đổi sang trạng thái ENABLED
                is_ready = export_btn.is_enabled()
                if not is_ready:
                    for _ in range(10):
                        time.sleep(0.2)
                        if export_btn.is_enabled():
                            is_ready = True
                            break

                if not is_ready:
                    raise DownloadManagerError(
                        f"Nút 'Xuất xml' vẫn bị disabled sau khi chọn hóa đơn số {expected_key.sh_hoa_don}"
                    )

                logger.debug(f"Nút 'Xuất xml' đã enabled, kích hoạt download...")

                # 5. Kích hoạt và bắt sự kiện download
                temp_downloads_dir = self.download_manager.downloads_dir
                with page.expect_download(timeout=25000) as download_info:
                    export_btn.click()
                    logger.debug("Đã click nút 'Xuất xml', chờ nhận file...")

                    # Xử lý dropdown nếu có
                    try:
                        dd_opt = page.locator(
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('XML'), "
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('xml'), "
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('zip'), "
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('ZIP'), "
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('Tải')"
                        ).first
                        if dd_opt.is_visible(timeout=800):
                            dd_opt.click()
                    except Exception:
                        pass

                # 6. Nhận và lưu file tải về
                download = download_info.value
                suggested_filename = download.suggested_filename or "invoice.zip"
                logger.info(f"Đã nhận file tải về: {suggested_filename}")

                # Bảo vệ an toàn: nếu vô tình tải về file Excel danh sách thì báo lỗi
                if suggested_filename.lower().endswith((".xlsx", ".xls")):
                    raise DownloadManagerError(
                        f"Cổng Thuế trả về file Excel ({suggested_filename}) thay vì ZIP/XML hóa đơn"
                    )

                temp_save_path = temp_downloads_dir / suggested_filename
                if temp_save_path.exists():
                    temp_save_path = temp_downloads_dir / f"{time.time_ns()}_{suggested_filename}"

                download.save_as(str(temp_save_path))
                logger.info(f"Đã lưu file tạm: {temp_save_path.name}")

                # 7. Xử lý ZIP → trích xuất invoice.xml → lưu ALLINVOICE/
                _, invoice_header = self.download_manager.process_downloaded_zip(
                    zip_path=temp_save_path,
                    expected_key=expected_key,
                    retry_count=attempt,
                )
                return invoice_header

            except SessionExpiredError:
                raise
            except Exception as e:
                self._close_modal_if_open(page)
                if attempt < retry_limit:
                    logger.warning(
                        f"Thử lại hóa đơn {expected_key.sh_hoa_don} "
                        f"(lần {attempt + 1}/{retry_limit}): {e}"
                    )
                    time.sleep(1.5)
                else:
                    logger.error(f"Thất bại khi tải hóa đơn {expected_key.sh_hoa_don}: {e}")
                    self.download_manager._record_failure(
                        expected_key=expected_key,
                        error_msg=str(e),
                        temp_zip_name="",
                        retry_count=attempt,
                    )
                    return None

        return None

    def _close_modal_if_open(self, page: Page):
        """Closes Ant Design modal dialog if currently displayed."""
        try:
            modals = page.locator(".ant-modal:visible, div[role='dialog']:visible")
            if modals.count() == 0:
                return

            try:
                page.keyboard.press("Escape")
                time.sleep(0.3)
            except Exception:
                pass

            close_selectors = [
                ".ant-modal:visible .ant-modal-close",
                ".ant-modal:visible button:has-text('Đóng')",
                ".ant-modal:visible .ant-modal-footer button:has-text('Đóng')",
                ".ant-modal:visible button:has-text('OK')",
                "div[role='dialog']:visible .ant-modal-close",
                "div[role='dialog']:visible button:has-text('Đóng')",
            ]
            for sel in close_selectors:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=400):
                    btn.click()
                    time.sleep(0.4)
                    break
        except Exception as e:
            logger.debug(f"Không có modal cần đóng hoặc đã đóng: {e}")

    def run_download_all(
        self,
        page: Page,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        max_invoices: Optional[int] = None,
    ) -> SummaryStats:
        """Processes all invoice rows across all available pages.

        - Respects progress callback(current_index, total, status_text).
        - Skips already extracted invoices.
        - Supports graceful cancellation via request_stop().
        """
        self._stop_requested = False
        processed_count = 0
        current_page_num = 1

        while not self._stop_requested:
            self._wait_for_table_loaded(page)
            col_map = self._get_column_map(page)
            rows = self._get_table_rows(page)
            row_count = rows.count()
            logger.info(f"Trang {current_page_num}: Tìm thấy {row_count} dòng hóa đơn.")

            if row_count == 0:
                logger.info("Không có dòng hóa đơn nào trên trang hiện tại.")
                break

            seen_keys_on_page = set()

            for i in range(row_count):
                if self._stop_requested:
                    logger.info("Đã nhận yêu cầu dừng từ người dùng.")
                    break

                if max_invoices and processed_count >= max_invoices:
                    logger.info(f"Đã đạt số lượng tối đa cần tải ({max_invoices}).")
                    break

                # Re-query rows in case DOM refreshed
                current_rows = self._get_table_rows(page)
                if i >= current_rows.count():
                    break
                row = current_rows.nth(i)

                row_data = self.extract_row_data(row, col_map=col_map)
                candidate_key = InvoiceKey(
                    mst_nguoi_ban=row_data.get("mst_nguoi_ban", ""),
                    kh_hoa_don=row_data.get("kh_hoa_don", ""),
                    sh_hoa_don=row_data.get("sh_hoa_don", ""),
                    ngay_lap=row_data.get("ngay_lap", ""),
                )
                key_str = candidate_key.normalized_key()

                # Deduplicate fixed-column duplicate elements on the same page
                unique_row_id = f"{candidate_key.sh_hoa_don}_{candidate_key.kh_hoa_don}_{candidate_key.ngay_lap}"
                if unique_row_id in seen_keys_on_page and candidate_key.sh_hoa_don:
                    continue
                seen_keys_on_page.add(unique_row_id)

                # Check if already processed
                if self.download_manager.manifest_db.is_invoice_completed(
                    invoice_key=key_str,
                    sh_hoa_don=candidate_key.sh_hoa_don,
                    kh_hoa_don=candidate_key.kh_hoa_don,
                ):
                    logger.info(f"Hóa đơn {candidate_key.sh_hoa_don} ({candidate_key.kh_hoa_don}) đã hoàn thành trước đó. Bỏ qua.")
                    if progress_callback:
                        progress_callback(processed_count + 1, row_count, f"Bỏ qua (đã có): {candidate_key.sh_hoa_don}")
                    processed_count += 1
                    continue

                if progress_callback:
                    progress_callback(processed_count + 1, row_count, f"Đang tải: {candidate_key.sh_hoa_don}")

                # Download invoice
                self.download_invoice_row(page, row, row_data)
                processed_count += 1

                # Polite delay between downloads
                time.sleep(self.polite_delay_seconds)

            if self._stop_requested or (max_invoices and processed_count >= max_invoices):
                break

            # Handle pagination
            next_selectors = [
                "button:has(.anticon-right):not([disabled])",
                ".ant-pagination-next:not(.ant-pagination-disabled) button",
                "li.ant-pagination-next:not(.ant-pagination-disabled) button",
                "li.ant-pagination-next:not(.ant-pagination-disabled) a",
                "li.ant-pagination-next:not(.ant-pagination-disabled) .ant-pagination-item-link",
                ".ant-pagination-next:not(.ant-pagination-disabled)",
                "button[aria-label='Next Page']:not([disabled])",
                "button:has-text('>'):not([disabled])",
            ]
            next_btn = None
            for sel in next_selectors:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1200):
                    next_btn = btn
                    break

            if next_btn:
                logger.info("Chuyển sang trang tiếp theo...")
                next_btn.click()
                current_page_num += 1
                time.sleep(1.5)
            else:
                logger.info("Đã duyệt hết tất cả các trang.")
                break

        return self.download_manager.manifest_db.get_summary_stats()
