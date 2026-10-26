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

        # 1. Use column mapping if detected
        if col_map:
            for field, idx in col_map.items():
                if idx < cell_count:
                    data[field] = cell_texts[idx]

        # 2. Positional fallback if primary fields still missing
        if not data["sh_hoa_don"] and cell_count >= 5:
            # Check if first cell is checkbox column
            offset = 1 if (cell_count > 6 and not cell_texts[0]) else 0
            if cell_count > offset + 4:
                data["stt"] = cell_texts[offset]
                data["kh_mau_so"] = cell_texts[offset + 1]
                data["kh_hoa_don"] = cell_texts[offset + 2]
                data["sh_hoa_don"] = cell_texts[offset + 3].strip()
                data["ngay_lap"] = cell_texts[offset + 4].strip()

        # 3. Pattern-matching fallback across all cells for critical fields
        for txt in cell_texts:
            # Match Date (DD/MM/YYYY)
            if not data["ngay_lap"] and re.search(r"\b\d{2}/\d{2}/\d{4}\b", txt):
                data["ngay_lap"] = re.search(r"\b\d{2}/\d{2}/\d{4}\b", txt).group(0)

            # Match MST (10 or 13-14 digits)
            if not data["mst_nguoi_ban"] and re.search(r"\b\d{10}(?:-\d{3})?\b", txt):
                data["mst_nguoi_ban"] = re.search(r"\b\d{10}(?:-\d{3})?\b", txt).group(0)

            # Match Invoice Symbol (e.g. C26TNT, 1C23TLL)
            if not data["kh_hoa_don"] and re.search(r"\b[1-9]?[A-Z]\d{2}[A-Z0-9]{2,4}\b", txt):
                data["kh_hoa_don"] = re.search(r"\b[1-9]?[A-Z]\d{2}[A-Z0-9]{2,4}\b", txt).group(0)

        # Clean invoice number
        if data["sh_hoa_don"]:
            data["sh_hoa_don"] = "".join(c for c in data["sh_hoa_don"] if c.isdigit())

        # Inspect data-row-key attribute if present
        row_key = row.get_attribute("data-row-key") or ""
        if row_key and not data["mst_nguoi_ban"]:
            parts = row_key.split("_")
            for part in parts:
                if re.match(r"^\d{10}(?:-\d{3})?$", part):
                    data["mst_nguoi_ban"] = part
                    break

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

    def download_invoice_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        retry_limit: int = 2,
    ) -> Optional[InvoiceHeader]:
        """Executes the download workflow for a single invoice row:

        1. Clicks the row and ensures selection without unchecking.
        2. Finds and triggers the download button (toolbar, row action, or detail modal).
        3. Intercepts ZIP download and processes it.
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
                # 1. Click specifically on the first cell of the row (STT / Số HĐ)
                # This highlights and selects the row cleanly without ever clicking links in other columns
                row.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.3)

                cells = row.locator("td")
                if cells.count() >= 2:
                    cells.nth(0).click()
                else:
                    row.click()

                logger.debug(f"Đã click chọn dòng hóa đơn số {expected_key.sh_hoa_don}")
                time.sleep(0.5)

                # 2. Find the exact 'Xuất hóa đơn' (Xuất XML) button on the toolbar
                # Uses the exact SVG ID #icon_ketxuat / #clip-icon_ketxuat provided from actual portal HTML
                download_button = None
                exact_selectors = [
                    "button:has(#icon_ketxuat)",
                    "button:has(#clip-icon_ketxuat)",
                    "button:has(#Path_53113)",
                    "button:has(#Path_53114)",
                    "button:has([id*='ketxuat'])",
                    ".ant-btn:has(#icon_ketxuat)",
                    ".ant-btn:has(#clip-icon_ketxuat)",
                    ".ant-btn:has(#Path_53113)",
                    "button.ButtonAnt__IconButton-sc-p5q16s-1:has(svg [id*='ketxuat'])",
                    "button.ButtonAnt__IconButton-sc-p5q16s-1:has(#icon_ketxuat)",
                    "button[title*='Xuất xml']",
                    "button[title*='Xuất XML']",
                ]

                for sel in exact_selectors:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=500):
                        download_button = btn
                        break

                # Priority 2: 4th icon-only button in the toolbar group above table
                if not download_button:
                    icon_btns = page.locator(".ant-btn-icon-only, .ButtonAnt__IconButton-sc-p5q16s-1")
                    count = icon_btns.count()
                    if count >= 4:
                        cand = icon_btns.nth(3)
                        if cand.is_visible(timeout=300):
                            download_button = cand

                # Priority 3: Fallback button selectors
                if not download_button:
                    for sel in [
                        "button:has-text('Xuất XML')",
                        "button:has-text('Xuất xml')",
                        "button:has-text('Tải XML')",
                        "button:has-text('Tải hóa đơn')",
                        ".ant-btn:has(.anticon-download)",
                        ".ant-btn:has(.anticon-export)",
                    ]:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=300):
                            download_button = btn
                            break

                if not download_button:
                    raise DownloadManagerError(
                        f"Không tìm thấy nút 'Xuất XML' trên thanh công cụ cho hóa đơn số {expected_key.sh_hoa_don}"
                    )

                # 3. Intercept and trigger download
                temp_downloads_dir = self.download_manager.downloads_dir

                # Check if clicking button opens a dropdown menu (e.g. format choice: XML vs PDF)
                dropdown_item = None
                with page.expect_download(timeout=25000) as download_info:
                    download_button.click()
                    # Check if a dropdown menu popped up needing a sub-click
                    try:
                        dd_opt = page.locator(
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('XML'), "
                            ".ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu-item:has-text('Tải')"
                        ).first
                        if dd_opt.is_visible(timeout=1000):
                            dd_opt.click()
                    except Exception:
                        pass

                download = download_info.value
                suggested_filename = download.suggested_filename or "invoice.zip"
                temp_save_path = temp_downloads_dir / suggested_filename

                download.save_as(str(temp_save_path))
                logger.info(f"Đã nhận file tải về: {temp_save_path.name}")

                # 4. Close any opened modal to reset UI for next row
                self._close_modal_if_open(page)

                # 5. Process downloaded ZIP
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
                    logger.warning(f"Thử lại hóa đơn {expected_key.sh_hoa_don} (lần {attempt + 1}/{retry_limit}): {e}")
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
            close_btn = page.locator(".ant-modal-close, button:has-text('Đóng'), .ant-modal-footer button:has-text('Đóng')").first
            if close_btn.is_visible(timeout=800):
                close_btn.click()
                time.sleep(0.5)
        except Exception:
            pass

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
                "li.ant-pagination-next:not(.ant-pagination-disabled) button",
                "li.ant-pagination-next:not(.ant-pagination-disabled) a",
                "li.ant-pagination-next:not(.ant-pagination-disabled) .ant-pagination-item-link",
                ".ant-pagination-next:not(.ant-pagination-disabled)",
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
