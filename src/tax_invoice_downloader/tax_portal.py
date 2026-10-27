"""Tax portal interaction automation: navigating search, selecting invoice rows, triggering downloads, and handling pagination."""

import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple, Set
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from .models import InvoiceKey, InvoiceHeader, SummaryStats, ReconciliationReport
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
        """Finds table rows prioritizing the left fixed table (.ant-table-fixed-left)
        where visible, clickable cells and invoice details reside on Cổng Thuế.
        """
        selectors = [
            ".ant-table-fixed-left tbody.ant-table-tbody tr.ant-table-row",
            ".ant-table-fixed-left tbody tr.ant-table-row",
            "div.ant-table-scroll div.ant-table-body tr.ant-table-row",
            "div.ant-table-body table tbody tr.ant-table-row",
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
        """Định vị chính xác nút 'Xuất xml' trên thanh công cụ bảng.

        Quy tắc quan trọng từ giao diện Cổng Thuế và yêu cầu người dùng:
        - Thanh công cụ có 4 icon buttons bên phải:
          [0: Xem chi tiết] [1: In hóa đơn] [2: Xuất hóa đơn (Excel)] [3: Xuất xml (XML)]
        - Nút [2: Xuất hóa đơn] và nút [3: Xuất xml] dùng chung biểu tượng SVG (#icon_ketxuat, #Path_53113).
        - Nút [3: Xuất xml] luôn nằm BÊN PHẢI NGOÀI CÙNG (nằm phía sau nút Xuất hóa đơn).
        - TUYỆT ĐỐI KHÔNG dùng .first (sẽ chọn nhầm nút Xuất hóa đơn tải về file Excel).
        - Luôn chọn .last trong nhóm nút có icon ketxuat hoặc nút thứ 4 (nth(3)) của toolbar.
        """
        # 1. Nhóm nút có icon SVG #Path_53113, #Path_53114, #icon_ketxuat -> LẤY NÚT CUỐI CÙNG (.last)
        ketxuat_selectors = [
            ".ant-col button:has(#Path_53113)",
            ".ant-col button:has(#Path_53114)",
            ".ant-col button:has([data-name='Path 53113'])",
            ".ant-col button:has([data-name='Path 53114'])",
            ".ant-col button:has(#icon_ketxuat)",
            "button:has(#Path_53113)",
            "button:has(#Path_53114)",
            "button:has([data-name='Path 53113'])",
            "button:has([data-name='Path 53114'])",
            "button:has(#icon_ketxuat)",
            "button:has(svg path[d*='M10.54,4.4'])",
        ]
        for sel in ketxuat_selectors:
            loc = page.locator(sel)
            count = loc.count()
            if count > 0:
                cand = loc.last
                if cand.is_visible(timeout=300):
                    return cand

        # 2. Định danh theo title hoặc tooltip
        for sel in [
            "button[title*='xml' i]",
            "button[title*='XML' i]",
            "button[aria-label*='xml' i]",
            "button[aria-label*='XML' i]",
        ]:
            loc = page.locator(sel)
            if loc.count() > 0:
                cand = loc.last
                if cand.is_visible(timeout=300):
                    return cand

        # 3. Nút thứ 4 (ngoài cùng bên phải) trong nhóm icon button của thanh công cụ
        # Thứ tự các nút: [Xem (0)] [In (1)] [Kết xuất Excel (2)] [Xuất XML (3)]
        icon_btns = page.locator(".ant-col button.ButtonAnt__IconButton-sc-p5q16s-1, .ant-col button.ant-btn-icon-only")
        count = icon_btns.count()
        if count >= 4:
            cand = icon_btns.nth(3)  # Nút thứ 4 là Xuất XML
            if cand.is_visible(timeout=300):
                return cand
        elif count > 0:
            cand = icon_btns.last
            if cand.is_visible(timeout=300):
                return cand

        # 4. Fallback theo text nếu có
        for sel in ["button:has-text('Xuất XML')", "button:has-text('Xuất xml')", "button:has-text('Tải XML')"]:
            cand = page.locator(sel).last
            if cand.is_visible(timeout=300):
                return cand

        return None

    def _is_button_enabled(self, btn: Optional[Locator]) -> bool:
        """Kiểm tra nút có thực sự ở trạng thái sẵn sàng click không (không bị disabled)."""
        if not btn:
            return False
        try:
            if not btn.is_visible(timeout=200):
                return False
            if not btn.is_enabled():
                return False
            cls = btn.get_attribute("class") or ""
            if "disabled" in cls or "ant-btn-disabled" in cls:
                return False
            if btn.get_attribute("disabled") is not None:
                return False
            if btn.get_attribute("aria-disabled") == "true":
                return False
            return True
        except Exception:
            return False

    def _select_table_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        row_index: int = 0,
    ) -> bool:
        """Kích hoạt chọn dòng hóa đơn cho đến khi dòng được chọn hoặc nút 'Xuất xml' được kích hoạt."""
        row_key = row.get_attribute("data-row-key") or ""
        sh_hoa_don = row_data.get("sh_hoa_don", "")
        kh_hoa_don = row_data.get("kh_hoa_don", "")

        # 1. Cuộn đến dòng
        try:
            row.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass

        # 2. Thử click trực tiếp vào ô có chữ nhìn thấy được (Số HĐ hoặc Ký hiệu)
        target_cells = []
        if sh_hoa_don:
            target_cells.append(page.locator(f".ant-table-fixed-left tr td:has-text('{sh_hoa_don}')"))
            target_cells.append(page.locator(f"tr td:has-text('{sh_hoa_don}')"))
        if kh_hoa_don:
            target_cells.append(page.locator(f".ant-table-fixed-left tr td:has-text('{kh_hoa_don}')"))
            target_cells.append(page.locator(f"tr td:has-text('{kh_hoa_don}')"))
        target_cells.append(row.locator("td"))

        for cell_locator in target_cells:
            count = cell_locator.count()
            for idx in range(min(count, 4)):
                c = cell_locator.nth(idx)
                try:
                    if c.is_visible(timeout=150) and c.inner_text().strip():
                        c.click(timeout=600)
                        time.sleep(0.15)
                        export_btn = self._get_export_xml_button(page)
                        if export_btn and self._is_button_enabled(export_btn):
                            logger.debug(f"Đã chọn thành công dòng qua cell (text='{c.inner_text().strip()}')")
                            return True
                except Exception:
                    pass

        # 3. Kích hoạt sự kiện native click thông qua JavaScript trên tất cả phần tử tương ứng của dòng
        try:
            page.evaluate("""({ key, sh, rowIndex }) => {
                let targets = [];
                if (key) {
                    targets = Array.from(document.querySelectorAll(`tr[data-row-key="${key}"]`));
                }
                if (targets.length === 0 && sh) {
                    const rows = document.querySelectorAll('tr.ant-table-row');
                    targets = Array.from(rows).filter(r => r.innerText.includes(sh));
                }
                if (targets.length === 0) {
                    const fixedRows = document.querySelectorAll('.ant-table-fixed-left tbody tr.ant-table-row, tbody.ant-table-tbody tr.ant-table-row');
                    if (fixedRows[rowIndex]) targets = [fixedRows[rowIndex]];
                }
                targets.forEach(tr => {
                    tr.scrollIntoView({ block: 'nearest' });
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        tr.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                    Array.from(tr.querySelectorAll('td')).forEach(td => {
                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                            td.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                        });
                    });
                });
            }""", {"key": row_key, "sh": sh_hoa_don, "rowIndex": row_index})
            time.sleep(0.2)
            export_btn = self._get_export_xml_button(page)
            if export_btn and self._is_button_enabled(export_btn):
                logger.debug(f"Đã chọn thành công dòng qua JavaScript dispatch (key={row_key})")
                return True
        except Exception as e:
            logger.debug(f"JS row selection: {e}")

        # 4. Fallback click trực tiếp vào dòng
        try:
            row.click(force=True, timeout=600)
            time.sleep(0.15)
            export_btn = self._get_export_xml_button(page)
            if export_btn and self._is_button_enabled(export_btn):
                return True
        except Exception:
            pass

        return False

    def download_invoice_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        row_index: int = 0,
        source_page: int = 1,
        retry_limit: int = 2,
    ) -> Optional[InvoiceHeader]:
        """Tải XML một hóa đơn theo quy trình bắt buộc Mục 3 Bước B:
        1. Tạo thư mục tạm riêng biệt cho lượt tải (Mục 3 Bước C).
        2. Chọn dòng hóa đơn (hiện highlight dòng).
        3. Chờ nút 'Xuất xml' (nút thứ 4, ngoài cùng bên phải) sẵn sàng.
        4. Bấm 'Xuất XML' đúng một lần -> theo dõi file tải hoàn tất.
        5. Xác minh file tồn tại, không rỗng, ZIP mở được không lỗi CRC, XML parse được.
        6. Đối soát dữ liệu XML với dòng nguồn -> trích xuất và lưu ALLINVOICE/.
        7. Ghi nhận SUCCESS hoặc FAILED có mã lỗi chi tiết.
        """
        expected_key = InvoiceKey(
            mst_nguoi_ban=row_data.get("mst_nguoi_ban", ""),
            kh_hoa_don=row_data.get("kh_hoa_don", ""),
            sh_hoa_don=row_data.get("sh_hoa_don", ""),
            ngay_lap=row_data.get("ngay_lap", ""),
        )
        inv_key_str = expected_key.normalized_key()

        # Đánh dấu IN_PROGRESS trong manifest
        self.download_manager.manifest_db.upsert_manifest(
            invoice_key=inv_key_str,
            mst_nguoi_ban=expected_key.mst_nguoi_ban,
            kh_hoa_don=expected_key.kh_hoa_don,
            sh_hoa_don=expected_key.sh_hoa_don,
            ngay_lap=expected_key.ngay_lap,
            source_page=source_page,
            status="IN_PROGRESS",
        )

        logger.info(f"[BƯỚC B] Bắt đầu xử lý: Số={expected_key.sh_hoa_don}, Ký hiệu={expected_key.kh_hoa_don}, MST={expected_key.mst_nguoi_ban}")

        for attempt in range(retry_limit + 1):
            temp_dir: Optional[Path] = None
            try:
                # 1. Tạo thư mục tạm riêng biệt cho lượt tải này (Mục 3 Bước C)
                temp_dir = self.download_manager.create_isolated_temp_dir(inv_key_str)

                # 2. Chọn dòng hóa đơn trên bảng
                self._select_table_row(page, row, row_data, row_index=row_index)

                # 3. Định vị nút 'Xuất xml' (nút thứ 4, ngoài cùng bên phải)
                export_btn = self._get_export_xml_button(page)
                if not export_btn:
                    raise DownloadManagerError(
                        f"Không tìm thấy nút 'Xuất xml' trên thanh công cụ cho hóa đơn số {expected_key.sh_hoa_don}",
                        error_code="TIMEOUT_BUTTON",
                    )

                # 4. Chờ nút 'Xuất xml' sẵn sàng
                is_ready = self._is_button_enabled(export_btn)
                if not is_ready:
                    for _ in range(12):
                        time.sleep(0.15)
                        export_btn = self._get_export_xml_button(page)
                        if export_btn and self._is_button_enabled(export_btn):
                            is_ready = True
                            break

                if not is_ready:
                    # Thử click lại dòng lần cuối
                    try:
                        row.locator("td").nth(4).click(timeout=500)
                        time.sleep(0.2)
                        export_btn = self._get_export_xml_button(page)
                        is_ready = export_btn and self._is_button_enabled(export_btn)
                    except Exception:
                        pass

                if not is_ready:
                    raise DownloadManagerError(
                        f"Nút 'Xuất xml' vẫn bị disabled sau khi chọn hóa đơn số {expected_key.sh_hoa_don}",
                        error_code="TIMEOUT_BUTTON",
                    )

                logger.debug(f"Nút 'Xuất xml' đã sẵn sàng, kích hoạt download vào thư mục riêng...")

                # 5. Kích hoạt và bắt sự kiện download
                with page.expect_download(timeout=30000) as download_info:
                    export_btn.click()
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

                # 6. Nhận download và lưu vào thư mục tạm riêng biệt
                download = download_info.value
                filename = download.suggested_filename or "invoice.zip"
                temp_save_path = temp_dir / filename
                download.save_as(str(temp_save_path))

                # 7. Chờ file ổn định, không còn đuôi tạm
                stabilized_file = self.download_manager.wait_for_download_stabilization(temp_dir, timeout=25.0)

                # 8. Xác minh file, trích xuất XML và đối soát dữ liệu
                target_xml_path, invoice_header = self.download_manager.process_downloaded_zip(
                    zip_path=stabilized_file,
                    expected_key=expected_key,
                    source_page=source_page,
                    retry_count=attempt,
                )
                logger.info(f"[SUCCESS] Hóa đơn số {expected_key.sh_hoa_don} đã được lưu và xác minh hợp lệ.")
                return invoice_header

            except SessionExpiredError:
                raise
            except Exception as e:
                self._close_modal_if_open(page)
                error_code = getattr(e, "error_code", "PROCESS_ERROR")
                if attempt < retry_limit:
                    logger.warning(
                        f"Thử lại hóa đơn {expected_key.sh_hoa_don} (lần {attempt + 1}/{retry_limit}) - Mã lỗi: {error_code}: {e}"
                    )
                    time.sleep(1.2 * (attempt + 1))
                else:
                    logger.error(f"[FAILED] Thất bại sau {retry_limit + 1} lần thử cho hóa đơn {expected_key.sh_hoa_don}: {e}")
                    self.download_manager._record_failure(
                        expected_key=expected_key,
                        error_msg=str(e),
                        temp_zip_name="",
                        retry_count=attempt,
                        error_code=error_code,
                        source_page=source_page,
                    )
                    return None
            finally:
                # Dọn dẹp thư mục tạm của lượt thử nếu còn
                if temp_dir and temp_dir.exists():
                    try:
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        pass

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

    def get_announced_total_results(self, page: Page) -> Optional[int]:
        """Đọc tổng số kết quả hiển thị trên Cổng Thuế (ví dụ: 'Có 1.367 kết quả')."""
        try:
            candidates = [
                page.locator("text=/Có\\s+[\\d\\.,]+\\s+kết quả/i"),
                page.locator(".ant-table-pagination-total-text"),
                page.locator("div:has-text('kết quả')"),
            ]
            for cand in candidates:
                count = cand.count()
                for i in range(count):
                    txt = cand.nth(i).inner_text().strip()
                    m = re.search(r"Có\s+([\d\.,]+)\s+kết quả", txt, re.IGNORECASE)
                    if m:
                        raw = m.group(1).replace(".", "").replace(",", "").strip()
                        if raw.isdigit():
                            return int(raw)
        except Exception as e:
            logger.debug(f"Không thể đọc tổng số kết quả công bố: {e}")
        return None

    def _get_next_page_button(self, page: Page) -> Optional[Locator]:
        """Tìm nút chuyển trang kế tiếp trên Cổng Thuế nếu còn trang tiếp theo."""
        selectors = [
            ".ant-pagination-next:not(.ant-pagination-disabled) button",
            "li.ant-pagination-next:not(.ant-pagination-disabled) button",
            "li.ant-pagination-next:not(.ant-pagination-disabled) a",
            "li.ant-pagination-next:not(.ant-pagination-disabled) .ant-pagination-item-link",
            "button:has(.anticon-right):not([disabled])",
            "button:has(svg[data-icon='right']):not([disabled])",
            ".ant-pagination-next:not(.ant-pagination-disabled)",
            "button[aria-label='Next Page']:not([disabled])",
            "button:has-text('>'):not([disabled])",
        ]
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                btn = loc.first
                try:
                    if btn.is_visible(timeout=300) and btn.is_enabled():
                        cls = btn.get_attribute("class") or ""
                        parent_cls = ""
                        try:
                            parent_cls = btn.locator("..").get_attribute("class") or ""
                        except Exception:
                            pass
                        if "disabled" not in cls and "disabled" not in parent_cls:
                            return btn
                except Exception:
                    pass
        return None

    def _wait_for_page_transition(self, page: Page, old_first_key: str, timeout: float = 12.0):
        """Chờ bảng dữ liệu sang trang mới hoàn tất và nội dung dòng đầu tiên thay đổi."""
        start = time.time()
        time.sleep(0.4)
        while time.time() - start < timeout:
            self._wait_for_table_loaded(page)
            rows = self._get_table_rows(page)
            if rows.count() > 0:
                first_row_data = self.extract_row_data(rows.first)
                new_key = InvoiceKey(
                    mst_nguoi_ban=first_row_data.get("mst_nguoi_ban", ""),
                    kh_hoa_don=first_row_data.get("kh_hoa_don", ""),
                    sh_hoa_don=first_row_data.get("sh_hoa_don", ""),
                    ngay_lap=first_row_data.get("ngay_lap", ""),
                ).normalized_key()
                if not old_first_key or new_key != old_first_key:
                    logger.debug(f"Đã chuyển trang thành công (Dòng đầu mới: {first_row_data.get('sh_hoa_don')})")
                    time.sleep(0.3)
                    return
            time.sleep(0.3)

    def _build_reconciliation_report(
        self,
        announced_total: Optional[int],
        seen_source_keys: Dict[str, Dict[str, Any]],
        run_success_keys: Set[str],
        run_already_verified_keys: Set[str],
        run_failed_keys: Set[str],
    ) -> SummaryStats:
        """Thực hiện đối soát tổng số hóa đơn nguồn theo Mục 6 của FIX_TAI_THIEU_XML_TU_DONG.md."""
        source_count = max(len(seen_source_keys), announced_total or len(seen_source_keys))
        success_count = len(run_success_keys)
        already_verified_count = len(run_already_verified_keys)
        failed_count = len(run_failed_keys)
        pending_count = max(0, source_count - (success_count + already_verified_count + failed_count))
        missing_count = source_count - (success_count + already_verified_count)

        report = ReconciliationReport(
            source_count=source_count,
            success_count=success_count,
            already_verified_count=already_verified_count,
            failed_count=failed_count,
            pending_count=pending_count,
            missing_invoice_count=missing_count,
        )
        is_balanced = report.verify_balance()

        logger.info("=" * 64)
        logger.info("           BÁO CÁO ĐỐI SOÁT HÓA ĐƠN NGUỒN (MỤC 6)")
        logger.info("=" * 64)
        logger.info(f"1. Tổng số hóa đơn nguồn (source_count)         : {source_count}")
        logger.info(f"2. Tải thành công đợt này (success_count)       : {success_count}")
        logger.info(f"3. Đã có từ trước (already_verified_count)      : {already_verified_count}")
        logger.info(f"4. Thất bại sau retry (failed_count)            : {failed_count}")
        logger.info(f"5. Chưa kịp xử lý (pending_count)               : {pending_count}")
        logger.info(f"6. Tổng số hóa đơn chưa có XML (missing_count)  : {missing_count}")
        logger.info(f"7. Trạng thái cân bằng công thức đối soát       : {'ĐẠT (Khớp 100%)' if is_balanced else 'CẢNH BÁO: CHƯA KHỚP'}")
        logger.info("=" * 64)

        # Xuất missing_or_failed_invoices.csv nếu có hóa đơn lỗi hoặc thiếu (Mục 6)
        from .download_manager import BASE_DIR
        output_dir = BASE_DIR / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        missing_csv_path = output_dir / "missing_or_failed_invoices.csv"

        if missing_count > 0 or failed_count > 0:
            exported_cnt = self.download_manager.manifest_db.export_missing_or_failed_csv(missing_csv_path)
            report.csv_report_path = str(missing_csv_path)
            logger.info(f"Đã xuất danh sách {exported_cnt} hóa đơn thiếu/lỗi ra file: {missing_csv_path}")

        return SummaryStats(
            so_dong_tim_thay=source_count,
            so_da_tai=success_count + already_verified_count,
            so_xml_thanh_cong=success_count,
            so_loi=failed_count,
            so_bo_qua=already_verified_count,
            so_cho_xu_ly=pending_count,
            so_thieu=missing_count,
            reconciliation=report,
        )

    def run_download_all(
        self,
        page: Page,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        max_invoices: Optional[int] = None,
    ) -> SummaryStats:
        """Thực hiện tải tuần tự từng hóa đơn một theo quy trình bắt buộc trong FIX_TAI_THIEU_XML_TU_DONG.md:
        - Xử lý tuần tự: Chọn hóa đơn -> Xuất XML -> Đợi file tải hoàn tất -> Kiểm tra file -> Ghi nhận kết quả -> Mới chuyển sang hóa đơn tiếp theo.
        - Không bỏ sót bất kỳ hóa đơn nào.
        - Đối soát tổng số hóa đơn nguồn (source_count).
        - Xuất báo cáo missing_or_failed_invoices.csv nếu có hóa đơn lỗi/thiếu.
        """
        self._stop_requested = False
        current_page_num = 1
        processed_count = 0

        # Bước A: Xác định tổng số hóa đơn nguồn theo công bố trên Cổng Thuế
        announced_total = self.get_announced_total_results(page)
        if announced_total:
            logger.info(f"[BƯỚC A] Tổng số hóa đơn công bố trên Cổng Thuế: {announced_total} kết quả.")
        else:
            logger.info("[BƯỚC A] Không đọc được số tổng công bố, sẽ tính tổng nguồn theo số dòng thực tế quét được.")

        seen_source_keys: Dict[str, Dict[str, Any]] = {}
        run_success_keys: Set[str] = set()
        run_already_verified_keys: Set[str] = set()
        run_failed_keys: Set[str] = set()

        while not self._stop_requested:
            self._wait_for_table_loaded(page)
            col_map = self._get_column_map(page)
            rows = self._get_table_rows(page)
            row_count = rows.count()

            logger.info(f"--- Đang xử lý Trang {current_page_num}: Có {row_count} dòng hóa đơn ---")

            if row_count == 0:
                logger.info(f"Trang {current_page_num} không có dòng hóa đơn nào.")
                break

            # Ghi nhận toàn bộ hóa đơn trên trang hiện tại vào danh sách nguồn
            page_invoices: List[Tuple[int, InvoiceKey, Dict[str, str]]] = []
            for i in range(row_count):
                row_el = rows.nth(i)
                data = self.extract_row_data(row_el, col_map=col_map)
                inv_key = InvoiceKey(
                    mst_nguoi_ban=data.get("mst_nguoi_ban", ""),
                    kh_hoa_don=data.get("kh_hoa_don", ""),
                    sh_hoa_don=data.get("sh_hoa_don", ""),
                    ngay_lap=data.get("ngay_lap", ""),
                )
                k_str = inv_key.normalized_key()
                if k_str not in seen_source_keys:
                    seen_source_keys[k_str] = {
                        "key": inv_key,
                        "data": data,
                        "source_page": current_page_num,
                    }
                    existing_status = self.download_manager.manifest_db.get_invoice_status(k_str)
                    if not existing_status:
                        self.download_manager.manifest_db.upsert_manifest(
                            invoice_key=k_str,
                            mst_nguoi_ban=inv_key.mst_nguoi_ban,
                            kh_hoa_don=inv_key.kh_hoa_don,
                            sh_hoa_don=inv_key.sh_hoa_don,
                            ngay_lap=inv_key.ngay_lap,
                            source_page=current_page_num,
                            status="PENDING",
                        )
                page_invoices.append((i, inv_key, data))

            # Xử lý tuần tự từng hóa đơn trên trang
            for row_idx, inv_key, row_data in page_invoices:
                if self._stop_requested:
                    logger.info("Nhận được tín hiệu dừng từ người dùng.")
                    break

                if max_invoices and processed_count >= max_invoices:
                    logger.info(f"Đã đạt số lượng tối đa cần tải ({max_invoices}).")
                    break

                k_str = inv_key.normalized_key()
                total_target = announced_total or len(seen_source_keys)

                # 1. Kiểm tra xem hóa đơn này đã được xác minh hợp lệ trước đó chưa (ALREADY_VERIFIED)
                if self.download_manager.manifest_db.is_invoice_completed(
                    invoice_key=k_str,
                    sh_hoa_don=inv_key.sh_hoa_don,
                    kh_hoa_don=inv_key.kh_hoa_don,
                    allinvoice_dir=self.download_manager.allinvoice_dir,
                ):
                    logger.info(f"[ALREADY_VERIFIED] Hóa đơn {inv_key.sh_hoa_don} ({inv_key.kh_hoa_don}) đã có XML hợp lệ trên ổ đĩa. Bỏ qua.")
                    self.download_manager.manifest_db.upsert_manifest(
                        invoice_key=k_str,
                        mst_nguoi_ban=inv_key.mst_nguoi_ban,
                        kh_hoa_don=inv_key.kh_hoa_don,
                        sh_hoa_don=inv_key.sh_hoa_don,
                        ngay_lap=inv_key.ngay_lap,
                        source_page=current_page_num,
                        status="ALREADY_VERIFIED",
                    )
                    run_already_verified_keys.add(k_str)
                    processed_count += 1
                    if progress_callback:
                        progress_callback(processed_count, total_target, f"Đã có: {inv_key.sh_hoa_don}")
                    continue

                # 2. Re-query row element trên DOM để tránh lỗi stale DOM element
                current_rows = self._get_table_rows(page)
                if row_idx >= current_rows.count():
                    row_el = current_rows.last
                else:
                    row_el = current_rows.nth(row_idx)

                if progress_callback:
                    progress_callback(processed_count + 1, total_target, f"Đang tải: {inv_key.sh_hoa_don}")

                # 3. Thực hiện tải tuần tự hóa đơn hiện tại
                header = self.download_invoice_row(
                    page=page,
                    row=row_el,
                    row_data=row_data,
                    row_index=row_idx,
                    source_page=current_page_num,
                )

                if header:
                    run_success_keys.add(k_str)
                else:
                    run_failed_keys.add(k_str)

                processed_count += 1

                # Polite delay giữa các lần tải
                time.sleep(self.polite_delay_seconds)

            if self._stop_requested or (max_invoices and processed_count >= max_invoices):
                break

            # Bước chuyển trang tiếp theo
            next_btn = self._get_next_page_button(page)
            if next_btn:
                logger.info(f"Đang chuyển từ Trang {current_page_num} sang Trang {current_page_num + 1}...")
                first_key_before = page_invoices[0][1].normalized_key() if page_invoices else ""
                next_btn.click()
                current_page_num += 1

                self._wait_for_page_transition(page, old_first_key=first_key_before, timeout=12.0)
            else:
                logger.info(f"Đã duyệt hết tất cả các trang (kết thúc ở Trang {current_page_num}).")
                break

        # Bước 6: Đối soát tổng số hóa đơn nguồn (Reconciliation)
        final_stats = self._build_reconciliation_report(
            announced_total=announced_total,
            seen_source_keys=seen_source_keys,
            run_success_keys=run_success_keys,
            run_already_verified_keys=run_already_verified_keys,
            run_failed_keys=run_failed_keys,
        )
        return final_stats
