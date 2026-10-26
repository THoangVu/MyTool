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

    def extract_row_data(self, row: Locator) -> Dict[str, str]:
        """Extracts text from cells in an Ant Design table row."""
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

        # Fallback mapping based on typical tax portal column positions:
        # 0: STT, 1: MST Mua, 2: Mẫu số, 3: Ký hiệu, 4: Số HĐ, 5: Ngày lập, 6: Người bán, 7: Tiền chưa thuế, 8: Thuế, 11: Tổng thanh toán
        if cell_count >= 6:
            data["stt"] = cell_texts[0]
            data["mst_nguoi_mua"] = cell_texts[1]
            data["kh_mau_so"] = cell_texts[2]
            data["kh_hoa_don"] = cell_texts[3]
            # Clean invoice number
            raw_sh = cell_texts[4]
            data["sh_hoa_don"] = raw_sh.strip()
            data["ngay_lap"] = cell_texts[5]

        if cell_count >= 7:
            seller_info = cell_texts[6]
            data["thong_tin_nguoi_ban"] = seller_info
            # Try to extract 10-14 digit tax code from seller info
            mst_match = re.search(r"\b\d{10}(?:-\d{3})?\b", seller_info)
            if mst_match:
                data["mst_nguoi_ban"] = mst_match.group(0)

        # Also inspect data-row-key attribute if present
        row_key = row.get_attribute("data-row-key") or ""
        if row_key and not data["mst_nguoi_ban"]:
            # data-row-key often contains {id}_{mst}_{kh}_{sh}
            parts = row_key.split("_")
            for part in parts:
                if re.match(r"^\d{10}(?:-\d{3})?$", part):
                    data["mst_nguoi_ban"] = part
                    break

        return data

    def download_invoice_row(
        self,
        page: Page,
        row: Locator,
        row_data: Dict[str, str],
        retry_limit: int = 2,
    ) -> Optional[InvoiceHeader]:
        """Executes the download workflow for a single invoice row:

        1. Clicks the row.
        2. Waits for detail modal / action toolbar.
        3. Clicks download button and intercepts the download.
        4. Processes ZIP via DownloadManager.
        """
        self.check_session(page)
        expected_key = InvoiceKey(
            mst_nguoi_ban=row_data.get("mst_nguoi_ban", ""),
            kh_hoa_don=row_data.get("kh_hoa_don", ""),
            sh_hoa_don=row_data.get("sh_hoa_don", ""),
            ngay_lap=row_data.get("ngay_lap", ""),
        )

        logger.info(f"Bắt đầu xử lý hóa đơn: Số={expected_key.sh_hoa_don}, Ký hiệu={expected_key.kh_hoa_don}")

        for attempt in range(retry_limit + 1):
            try:
                # Scroll row into view and click
                row.scroll_into_view_if_needed(timeout=3000)
                time.sleep(0.3)
                row.click()
                logger.debug(f"Đã click chọn dòng hóa đơn số {expected_key.sh_hoa_don}")
                time.sleep(0.8)

                # Find download trigger
                download_button = None
                selectors = [
                    # Modal / dialog buttons
                    ".ant-modal button:has-text('Tải về')",
                    ".ant-modal button:has-text('Tải XML')",
                    ".ant-modal button:has-text('XML')",
                    ".ant-modal .ant-btn-primary:has-text('Tải')",
                    # Toolbar buttons outside modal
                    "button:has-text('Tải về')",
                    "button:has-text('Tải XML')",
                    "button:has-text('Xuất XML')",
                    "button:has-text('Tải hóa đơn')",
                    ".ant-btn:has(.anticon-download)",
                    "a:has-text('Tải về')",
                    "button:has-text('XML')",
                ]

                for sel in selectors:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        download_button = btn
                        break

                if not download_button:
                    # If button not found, try double click or row action button
                    action_btn = row.locator("button, a, i.anticon-download").first
                    if action_btn.is_visible(timeout=1000):
                        download_button = action_btn

                if not download_button:
                    raise DownloadManagerError(
                        f"Không tìm thấy nút tải XML cho hóa đơn số {expected_key.sh_hoa_don}"
                    )

                # Trigger download and intercept
                temp_downloads_dir = self.download_manager.downloads_dir
                with page.expect_download(timeout=20000) as download_info:
                    download_button.click()

                download = download_info.value
                suggested_filename = download.suggested_filename or "invoice.zip"
                temp_save_path = temp_downloads_dir / suggested_filename

                # Avoid collision in temp folder
                if temp_save_path.exists():
                    temp_save_path = temp_downloads_dir / f"{time.time_ns()}_{suggested_filename}"

                download.save_as(str(temp_save_path))
                logger.info(f"Đã nhận file tải về: {temp_save_path.name}")

                # Close any opened modal to reset UI for next row
                self._close_modal_if_open(page)

                # Process downloaded ZIP
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
            close_btn = page.locator(".ant-modal-close, button:has-text('Đóng'), .ant-modal-footer button").first
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
        self.check_session(page)
        processed_count = 0
        current_page_num = 1

        while not self._stop_requested:
            self._wait_for_table_loaded(page)
            rows = page.locator("table tbody tr.ant-table-row, div.ant-table-body tr.ant-table-row")
            row_count = rows.count()
            logger.info(f"Trang {current_page_num}: Tìm thấy {row_count} dòng hóa đơn.")

            if row_count == 0:
                logger.info("Không có dữ liệu hóa đơn trên trang hiện tại.")
                break

            for i in range(row_count):
                if self._stop_requested:
                    logger.info("Đã nhận yêu cầu dừng từ người dùng.")
                    break

                if max_invoices and processed_count >= max_invoices:
                    logger.info(f"Đã đạt số lượng tối đa cần tải ({max_invoices}).")
                    break

                row = rows.nth(i)
                row_data = self.extract_row_data(row)
                candidate_key = InvoiceKey(
                    mst_nguoi_ban=row_data.get("mst_nguoi_ban", ""),
                    kh_hoa_don=row_data.get("kh_hoa_don", ""),
                    sh_hoa_don=row_data.get("sh_hoa_don", ""),
                    ngay_lap=row_data.get("ngay_lap", ""),
                )
                key_str = candidate_key.normalized_key()

                # Check if already processed
                if key_str and self.download_manager.manifest_db.is_invoice_completed(key_str):
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
            next_btn = page.locator("li.ant-pagination-next:not(.ant-pagination-disabled) button, li.ant-pagination-next:not(.ant-pagination-disabled) a").first
            if next_btn.is_visible(timeout=2000):
                logger.info("Chuyển sang trang tiếp theo...")
                next_btn.click()
                current_page_num += 1
                time.sleep(1.5)
            else:
                logger.info("Đã duyệt hết tất cả các trang.")
                break

        return self.download_manager.manifest_db.get_summary_stats()
