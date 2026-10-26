"""Browser session manager using Playwright persistent context to maintain user sessions."""

import os
from pathlib import Path
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright

from .logging_config import setup_logger

logger = setup_logger("browser_session")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BROWSER_PROFILE_DIR = BASE_DIR / "browser_profile"
DOWNLOADS_DIR = BASE_DIR / "downloads"
DEFAULT_PORTAL_URL = "https://hoadondientu.gdt.gov.vn"


class BrowserSessionManager:
    """Manages persistent Chromium browser context for user login and automated actions."""

    def __init__(
        self,
        profile_dir: Optional[Path] = None,
        downloads_dir: Optional[Path] = None,
        portal_url: str = DEFAULT_PORTAL_URL,
    ):
        self.profile_dir = profile_dir or BROWSER_PROFILE_DIR
        self.downloads_dir = downloads_dir or DOWNLOADS_DIR
        self.portal_url = portal_url
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    def launch_browser(self, headless: bool = False) -> Page:
        """Launches Chromium with persistent profile to preserve cookies/session."""
        if self._page and not self._page.is_closed():
            logger.info("Trình duyệt đã mở sẵn.")
            return self._page

        logger.info(f"Đang mở trình duyệt với hồ sơ: {self.profile_dir} (headless={headless})")
        self._playwright = sync_playwright().start()

        # Launch persistent context
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=headless,
            accept_downloads=True,
            downloads_path=str(self.downloads_dir),
            viewport={"width": 1366, "height": 768},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

        # Navigate to portal if not already there
        current_url = self._page.url
        if not current_url or current_url == "about:blank":
            logger.info(f"Điều hướng tới cổng Thuế: {self.portal_url}")
            try:
                self._page.goto(self.portal_url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Không thể mở tự động trang chủ (người dùng có thể tải lại): {e}")

        # Dismiss initial announcement modal if present
        self.dismiss_announcement_modal(self._page)

        return self._page

    def dismiss_announcement_modal(self, page: Optional[Page] = None):
        """Dismisses the startup notice/announcement popup modal from the Tax department if present."""
        p = page or self._page
        if not p or p.is_closed():
            return
        try:
            # Check for notification modal
            notice_modal = p.locator(".ant-modal:has-text('THÔNG BÁO'), .ant-modal:has-text('Thông báo')").first
            if notice_modal.is_visible(timeout=2500):
                close_btn = notice_modal.locator(".ant-modal-close, button:has-text('Đóng'), button:has-text('OK')").first
                if close_btn.is_visible(timeout=1000):
                    close_btn.click()
                    logger.info("Đã tự động đóng cửa sổ Thông báo ban đầu của Cục Thuế.")
        except Exception as e:
            logger.debug(f"Không có modal thông báo cần đóng: {e}")

    def check_login_status(self, page: Optional[Page] = None) -> Tuple[bool, str]:
        """Checks whether user is currently logged into the tax portal.

        Returns (is_logged_in, status_description).
        """
        p = page or self._page
        if not p or p.is_closed():
            return False, "Trình duyệt chưa mở"

        try:
            url = p.url.lower()

            # Check if clearly on login screen
            if "dang-nhap" in url or "login" in url:
                return False, "Đang ở trang đăng nhập. Vui lòng nhập tài khoản và giải mã CAPTCHA."

            # Check if password input is visible (login modal open)
            pwd_input = p.locator("input[type='password']").first
            if pwd_input.is_visible(timeout=1000):
                return False, "Cửa sổ đăng nhập đang mở. Vui lòng hoàn thành đăng nhập và giải CAPTCHA."

            # Check for definitive logged-in indicators: logout button or user greeting
            if p.locator("text=Đăng xuất").first.is_visible(timeout=1000):
                return True, "Đã đăng nhập thành công (tìm thấy nút Đăng xuất)"

            # Check for login button on page header
            login_btn = p.locator("button:has-text('Đăng nhập'), a:has-text('Đăng nhập'), .ant-btn:has-text('Đăng nhập')").first
            if login_btn.is_visible(timeout=1000):
                return False, "Chưa đăng nhập. Vui lòng bấm 'Đăng nhập' trên trang thuế và xác thực."

            # Check if Tra cứu menu is available in logged-in state (user dropdown present)
            if p.locator(".ant-dropdown-link, .user-info, .ant-avatar").first.is_visible(timeout=1000):
                return True, "Đã đăng nhập thành công"

            return False, "Chưa xác nhận trạng thái đăng nhập. Vui lòng kiểm tra lại trên trình duyệt."

        except Exception as e:
            logger.debug(f"Lỗi kiểm tra session: {e}")
            return False, f"Lỗi kiểm tra session: {e}"

    def close(self):
        """Closes browser context and playwright instance cleanly."""
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            self._page = None
            logger.info("Đã đóng phiên trình duyệt.")
        except Exception as e:
            logger.warning(f"Lỗi khi đóng trình duyệt: {e}")
