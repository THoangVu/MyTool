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

            # 1. Check if definitely logged in by URL
            if "/tra-cuu" in url or "/hoa-don" in url or "/quan-ly" in url:
                return True, "Đã đăng nhập thành công (đang ở trang tra cứu)"

            # 2. Check for authenticated menus or tabs
            authenticated_selectors = [
                "text=Tra cứu hóa đơn",
                "text=Hóa đơn điện tử mua vào",
                "text=Tra cứu hóa đơn điện tử mua vào",
                "text=Đăng xuất",
                ".ant-dropdown-link",
                ".user-info",
                "a[href*='tra-cuu']",
            ]
            for sel in authenticated_selectors:
                try:
                    if p.locator(sel).first.is_visible(timeout=800):
                        return True, "Đã đăng nhập thành công (tìm thấy menu Tra cứu / Đăng xuất)"
                except Exception:
                    pass

            # 3. Check browser localStorage / sessionStorage for JWT / auth tokens
            try:
                has_auth_token = p.evaluate("""() => {
                    try {
                        const items = { ...localStorage, ...sessionStorage };
                        for (const [k, v] of Object.entries(items)) {
                            const key = k.toLowerCase();
                            const val = typeof v === 'string' ? v.toLowerCase() : '';
                            if (key.includes('token') || key.includes('auth') || key.includes('user') || key.includes('mst') || val.includes('bearer')) {
                                if (v && v.length > 5) return true;
                            }
                        }
                    } catch (e) {}
                    return false;
                }""")
                if has_auth_token:
                    return True, "Đã đăng nhập thành công (tìm thấy phiên làm việc)"
            except Exception:
                pass

            # 4. Check if password input is currently visible (login modal is open)
            pwd_input = p.locator("input[type='password']").first
            if pwd_input.is_visible(timeout=500):
                return False, "Cửa sổ đăng nhập đang mở. Vui lòng hoàn thành đăng nhập và giải CAPTCHA."

            # 5. Check if user is on the guest homepage
            if p.locator("button:has-text('Đăng nhập')").first.is_visible(timeout=500):
                return False, "Chưa đăng nhập. Vui lòng bấm 'Đăng nhập' trên cổng Thuế và xác thực."

            # Default: if on portal without login form, allow with warning
            return True, "Phiên trình duyệt đang mở"

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
