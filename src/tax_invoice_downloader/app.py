"""Desktop GUI Application for Tax Invoice Downloader."""

import os
import sys
import time
import queue
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .models import InvoiceKey, InvoiceHeader, SummaryStats
from .logging_config import setup_logger, ManifestDB, LOGS_DIR
from .download_manager import DownloadManager
from .browser_session import BrowserSessionManager, DEFAULT_PORTAL_URL
from .tax_portal import TaxPortalAutomation, SessionExpiredError
from .excel_exporter import export_from_allinvoice_folder, DEFAULT_EXCEL_PATH

logger = setup_logger("app_desktop")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALLINVOICE_DIR = BASE_DIR / "ALLINVOICE"
OUTPUT_DIR = BASE_DIR / "output"


class BrowserWorker:
    """Dedicated background worker thread for all Playwright operations.
    Playwright Sync API requires all calls to run on the exact same thread that
    initialized sync_playwright() to avoid TargetClosedError / greenlet thread errors.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def _worker_loop(self):
        while True:
            task = self._queue.get()
            if task is None:
                break
            func, args, kwargs, callback, errback = task
            try:
                result = func(*args, **kwargs)
                if callback:
                    callback(result)
            except Exception as e:
                if errback:
                    errback(e)
            finally:
                self._queue.task_done()

    def submit(self, func, *args, callback=None, errback=None, **kwargs):
        self._queue.put((func, args, kwargs, callback, errback))

    def stop(self):
        self._queue.put(None)


class TaxInvoiceApp(tk.Tk):
    """Main Desktop UI for Tax Invoice Downloader."""

    def __init__(self):
        super().__init__()
        self.title("Tool Tự Động Tải XML Hóa Đơn Từ Cổng Thuế")
        self.geometry("980x740")
        self.minsize(880, 640)

        # Ensure directories
        ALLINVOICE_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        self.manifest_db = ManifestDB()
        self.download_manager = DownloadManager(manifest_db=self.manifest_db)
        self.browser_manager = BrowserSessionManager()
        self.automation = TaxPortalAutomation(download_manager=self.download_manager)
        self.browser_worker = BrowserWorker()

        self.is_running = False
        self.is_session_confirmed = False

        self._setup_styles()
        self._build_ui()
        self._load_initial_stats()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Palette
        primary = "#1F4E79"
        accent = "#0284C7"
        bg_light = "#F3F4F6"

        self.configure(bg=bg_light)
        style.configure("TFrame", background=bg_light)
        style.configure("TLabelframe", background=bg_light, font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=bg_light, foreground=primary, font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background=bg_light, font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=primary, background=bg_light)
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground="#4B5563", background=bg_light)

        # Buttons
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), foreground="#FFFFFF", background=primary)
        style.map("Primary.TButton", background=[("active", "#163857")])

        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), foreground="#FFFFFF", background="#059669")
        style.map("Action.TButton", background=[("active", "#047857")])

        style.configure("Stop.TButton", font=("Segoe UI", 9, "bold"), foreground="#FFFFFF", background="#DC2626")
        style.map("Stop.TButton", background=[("active", "#B91C1C")])

        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E5E7EB")
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=24)

    def _build_ui(self):
        container = ttk.Frame(self, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        # 1. Header Banner
        header_frame = ttk.Frame(container)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            header_frame,
            text="TỰ ĐỘNG TẢI HÓA ĐƠN ĐIỆN TỬ TỪ CỔNG THUẾ",
            style="Header.TLabel"
        ).pack(anchor=tk.W)
        ttk.Label(
            header_frame,
            text="Trích xuất chỉ invoice.xml vào ALLINVOICE • Tự động tổng hợp dữ liệu ra Excel • Tương thích đối chiếu iPOS",
            style="SubHeader.TLabel"
        ).pack(anchor=tk.W)

        # 2. Control Panels: Step 1 (Session) & Step 2 (Filter)
        top_grid = ttk.Frame(container)
        top_grid.pack(fill=tk.X, pady=(0, 10))

        # Panel 1: Phiên trình duyệt
        sess_frame = ttk.LabelFrame(top_grid, text="Bước 1: Phiên làm việc Cổng Thuế", padding=10)
        sess_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        sess_desc = ttk.Label(
            sess_frame,
            text="Mở trình duyệt để đăng nhập và giải mã CAPTCHA thủ công.\nPhiên được duy trì tự động cho các lần chạy sau.",
            foreground="#4B5563"
        )
        sess_desc.pack(anchor=tk.W, pady=(0, 8))

        sess_btn_box = ttk.Frame(sess_frame)
        sess_btn_box.pack(fill=tk.X)

        self.btn_open_browser = ttk.Button(
            sess_btn_box,
            text="🌐 1. Mở Cổng Thuế",
            style="Primary.TButton",
            command=self._open_browser_action
        )
        self.btn_open_browser.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_confirm_login = ttk.Button(
            sess_btn_box,
            text="✅ Đã đăng nhập, tiếp tục",
            style="Action.TButton",
            command=self._confirm_login_action
        )
        self.btn_confirm_login.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_check_login = ttk.Button(
            sess_btn_box,
            text="🔍 Kiểm tra Phiên",
            command=self._check_login_action
        )
        self.btn_check_login.pack(side=tk.LEFT)

        self.lbl_session_status = ttk.Label(
            sess_frame,
            text="Trạng thái: Chưa mở trình duyệt",
            font=("Segoe UI", 9, "italic"),
            foreground="#D97706"
        )
        self.lbl_session_status.pack(anchor=tk.W, pady=(6, 0))

        # Panel 2: Cài đặt và Hướng dẫn
        filter_frame = ttk.LabelFrame(top_grid, text="Bước 2: Hướng dẫn & Cài đặt tải", padding=10)
        filter_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        guide_lbl = ttk.Label(
            filter_frame,
            text="1. Trên web: Tra cứu ➔ Tra cứu hóa đơn ➔ Hóa đơn mua vào.\n"
                 "2. Tự chọn khoảng ngày & bấm 'Tìm kiếm' trên web.\n"
                 "3. Khi bảng kết quả hiện ra, bấm '🚀 2. Bắt đầu tải XML hóa đơn'.",
            foreground="#1F2937",
            font=("Segoe UI", 9)
        )
        guide_lbl.pack(anchor=tk.W, pady=(0, 6))

        sub_opts = ttk.Frame(filter_frame)
        sub_opts.pack(fill=tk.X)

        ttk.Label(sub_opts, text="Thời gian chờ:").pack(side=tk.LEFT, padx=(0, 4))
        self.delay_spin = ttk.Spinbox(sub_opts, from_=0.5, to=5.0, increment=0.5, width=5)
        self.delay_spin.set("1.0")
        self.delay_spin.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(sub_opts, text="giây/hóa đơn", foreground="#6B7280").pack(side=tk.LEFT)

        # 3. Action Toolbar: Step 3 (Download) & Step 4 (Export/View)
        action_bar = ttk.Frame(container)
        action_bar.pack(fill=tk.X, pady=(0, 10))

        self.btn_start = ttk.Button(
            action_bar,
            text="🚀 2. Bắt đầu tải XML hóa đơn",
            style="Action.TButton",
            command=self._start_download_action
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = ttk.Button(
            action_bar,
            text="⏹ Dừng",
            style="Stop.TButton",
            state=tk.DISABLED,
            command=self._stop_action
        )
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 16))

        self.btn_export = ttk.Button(
            action_bar,
            text="📊 Xuất Excel Tổng Hợp",
            command=self._export_excel_action
        )
        self.btn_export.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_open_allinvoice = ttk.Button(
            action_bar,
            text="📁 Mở Thư Mục ALLINVOICE",
            command=self._open_allinvoice_folder
        )
        self.btn_open_allinvoice.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_open_excel = ttk.Button(
            action_bar,
            text="📄 Mở File Excel",
            command=self._open_excel_file
        )
        self.btn_open_excel.pack(side=tk.LEFT)

        # 4. Progress and Status Bar
        prog_frame = ttk.Frame(container)
        prog_frame.pack(fill=tk.X, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(prog_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        self.lbl_status = ttk.Label(
            prog_frame,
            text="Sẵn sàng. Vui lòng mở Cổng Thuế và đăng nhập để bắt đầu.",
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(anchor=tk.W)

        # 5. Live Results Table
        table_frame = ttk.LabelFrame(container, text="Danh sách hóa đơn đã xử lý", padding=6)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        cols = ("time", "sh", "kh", "mst", "status", "xml_file", "err")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("time", text="Thời điểm")
        self.tree.heading("sh", text="Số HĐ")
        self.tree.heading("kh", text="Ký hiệu")
        self.tree.heading("mst", text="MST Người bán")
        self.tree.heading("status", text="Trạng thái")
        self.tree.heading("xml_file", text="File XML")
        self.tree.heading("err", text="Ghi chú / Lỗi")

        self.tree.column("time", width=120, anchor=tk.CENTER)
        self.tree.column("sh", width=90, anchor=tk.CENTER)
        self.tree.column("kh", width=80, anchor=tk.CENTER)
        self.tree.column("mst", width=110, anchor=tk.CENTER)
        self.tree.column("status", width=110, anchor=tk.CENTER)
        self.tree.column("xml_file", width=250, anchor=tk.W)
        self.tree.column("err", width=180, anchor=tk.W)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 6. Summary Footer Badges
        footer_frame = ttk.Frame(container)
        footer_frame.pack(fill=tk.X)

        self.lbl_stat_total = ttk.Label(footer_frame, text="Tìm thấy: 0", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_total.pack(side=tk.LEFT, padx=(0, 16))

        self.lbl_stat_success = ttk.Label(footer_frame, text="XML Thành công: 0", font=("Segoe UI", 9, "bold"), foreground="#059669")
        self.lbl_stat_success.pack(side=tk.LEFT, padx=(0, 16))

        self.lbl_stat_skipped = ttk.Label(footer_frame, text="Đã có (Bỏ qua): 0", font=("Segoe UI", 9, "bold"), foreground="#0284C7")
        self.lbl_stat_skipped.pack(side=tk.LEFT, padx=(0, 16))

        self.lbl_stat_errors = ttk.Label(footer_frame, text="Lỗi: 0", font=("Segoe UI", 9, "bold"), foreground="#DC2626")
        self.lbl_stat_errors.pack(side=tk.LEFT, padx=(0, 16))

    def _load_initial_stats(self):
        """Loads manifest statistics and populates tree with recent history."""
        try:
            stats = self.manifest_db.get_summary_stats()
            self._update_stats_display(stats)

            history = self.manifest_db.get_all_history()
            for h in history[:100]:
                parts = h.get("khoa_hoa_don", "").split("_")
                mst = parts[0] if len(parts) > 0 else ""
                kh = parts[1] if len(parts) > 1 else ""
                sh = parts[2] if len(parts) > 2 else ""

                status = h.get("trang_thai", "")
                tag = "success" if status in ("XML_EXTRACTED", "EXPORTED") else "fail"
                self.tree.insert("", tk.END, values=(
                    h.get("thoi_diem", ""),
                    sh,
                    kh,
                    mst,
                    status,
                    h.get("ten_xml_dau_ra", ""),
                    h.get("thong_bao_loi", ""),
                ), tags=(tag,))

            self.tree.tag_configure("success", foreground="#065F46")
            self.tree.tag_configure("fail", foreground="#991B1B")

        except Exception as e:
            logger.warning(f"Lỗi khởi tạo danh sách lịch sử: {e}")

    def _update_stats_display(self, stats: SummaryStats):
        self.lbl_stat_total.config(text=f"Tìm thấy: {stats.so_dong_tim_thay}")
        self.lbl_stat_success.config(text=f"XML Thành công: {stats.so_xml_thanh_cong}")
        self.lbl_stat_skipped.config(text=f"Đã có (Bỏ qua): {stats.so_bo_qua}")
        self.lbl_stat_errors.config(text=f"Lỗi: {stats.so_loi}")

    def _open_browser_action(self):
        """Launches browser with persistent context via dedicated browser worker thread."""
        self.lbl_session_status.config(text="Đang mở trình duyệt...", foreground="#D97706")
        self.btn_open_browser.config(state=tk.DISABLED)

        def _task():
            page = self.browser_manager.launch_browser(headless=False)
            logged_in, msg = self.browser_manager.check_login_status(page)
            return logged_in, msg

        def _success(result):
            self.btn_open_browser.config(state=tk.NORMAL)
            logged_in, msg = result
            if logged_in:
                self.lbl_session_status.config(text="● Đã đăng nhập Cổng Thuế", foreground="#059669")
            else:
                self.lbl_session_status.config(text=f"● {msg}", foreground="#D97706")

        def _error(err):
            self.btn_open_browser.config(state=tk.NORMAL)
            self.lbl_session_status.config(text=f"Lỗi mở trình duyệt: {err}", foreground="#DC2626")
            messagebox.showerror("Lỗi", f"Không thể mở trình duyệt: {err}")

        self.browser_worker.submit(_task, callback=lambda res: self.after(0, _success, res), errback=lambda e: self.after(0, _error, e))

    def _check_login_action(self):
        """Checks login status of active page via dedicated browser worker thread."""
        def _task():
            pages = self.browser_manager.context.pages if self.browser_manager.context else []
            page = pages[-1] if pages else self.browser_manager.page
            if not page:
                return False, "Trình duyệt chưa mở. Vui lòng bấm '1. Mở Cổng Thuế' trước."
            return self.browser_manager.check_login_status(page)

        def _success(result):
            logged_in, msg = result
            if logged_in:
                self.lbl_session_status.config(text="● Đã đăng nhập Cổng Thuế", foreground="#059669")
                messagebox.showinfo("Thành công", "Phiên đăng nhập hợp lệ! Bạn có thể bắt đầu tải hóa đơn.")
            else:
                self.lbl_session_status.config(text=f"● {msg}", foreground="#D97706")
                messagebox.showwarning("Chưa đăng nhập", msg)

        def _error(err):
            self.lbl_session_status.config(text=f"Lỗi kiểm tra phiên: {err}", foreground="#DC2626")
            messagebox.showerror("Lỗi", f"Lỗi kiểm tra phiên: {err}")

        self.browser_worker.submit(_task, callback=lambda res: self.after(0, _success, res), errback=lambda e: self.after(0, _error, e))

    def _confirm_login_action(self):
        """Allows user to manually confirm login as specified in SPEC section 6."""
        self.is_session_confirmed = True
        self.lbl_session_status.config(text="● Đã xác nhận đăng nhập Cổng Thuế", foreground="#059669")
        self.lbl_status.config(text="Sẵn sàng! Hãy vào 'Tra cứu hóa đơn mua vào', tìm kiếm và bấm '2. Bắt đầu tải XML hóa đơn'.")
        messagebox.showinfo(
            "Đã xác nhận",
            "Đã xác nhận phiên đăng nhập thành công!\n\n"
            "Tiếp theo trên trình duyệt:\n"
            "1. Vào: Tra cứu ➔ Tra cứu hóa đơn ➔ Hóa đơn mua vào\n"
            "2. Chọn khoảng ngày & bấm 'Tìm kiếm'\n"
            "3. Khi bảng kết quả hiện ra, bấm '2. Bắt đầu tải XML hóa đơn' trên Tool!"
        )

    def _start_download_action(self):
        """Starts automated invoice downloading from the active table on the browser worker thread."""
        if self.is_running:
            return

        try:
            delay = float(self.delay_spin.get())
        except ValueError:
            delay = 1.0

        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress_bar.start(10)
        self.lbl_status.config(text="Đang kết nối danh sách hóa đơn trên trình duyệt...")

        def _download_task():
            if not self.browser_manager.context or not self.browser_manager.context.pages:
                raise RuntimeError(
                    "Trình duyệt chưa được kết nối.\n\nVui lòng bấm '🌐 1. Mở Cổng Thuế' trước, sau đó đăng nhập và tìm kiếm danh sách hóa đơn."
                )

            # Search for page that has the invoice table or tax portal
            pages = self.browser_manager.context.pages
            target_page = None
            for p in reversed(pages):
                try:
                    if self.automation._get_table_rows(p).count() > 0:
                        target_page = p
                        break
                except Exception:
                    pass

            if not target_page:
                for p in reversed(pages):
                    if "gdt.gov.vn" in p.url:
                        target_page = p
                        break

            if not target_page:
                target_page = pages[-1]

            self.automation.polite_delay_seconds = delay

            def on_progress(current, total, status_text):
                self.after(0, lambda: self.lbl_status.config(text=f"Tiến độ: [{current}/{total}] {status_text}"))
                stats = self.manifest_db.get_summary_stats()
                self.after(0, lambda: self._update_stats_display(stats))

            return self.automation.run_download_all(target_page, progress_callback=on_progress)

        def _on_success(stats):
            self._cleanup_download_ui()
            self._refresh_history_table()
            messagebox.showinfo(
                "Hoàn thành",
                f"Đã hoàn thành lượt tải hóa đơn!\n"
                f"- Số XML thành công: {stats.so_xml_thanh_cong}\n"
                f"- Số bỏ qua (đã có): {stats.so_bo_qua}\n"
                f"- Số lỗi: {stats.so_loi}\n\n"
                f"Bạn có thể bấm 'Xuất Excel Tổng Hợp' để xem báo cáo đối chiếu."
            )

        def _on_error(err):
            self._cleanup_download_ui()
            if isinstance(err, SessionExpiredError):
                self.lbl_session_status.config(text="● Phiên hết hạn, cần đăng nhập lại", foreground="#DC2626")
                messagebox.showwarning("Hết phiên", str(err))
            else:
                logger.error(f"Lỗi trong quá trình tải: {err}", exc_info=True)
                messagebox.showerror("Thông báo", str(err))

        self.browser_worker.submit(
            _download_task,
            callback=lambda res: self.after(0, _on_success, res),
            errback=lambda e: self.after(0, _on_error, e)
        )

    def _cleanup_download_ui(self):
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.lbl_status.config(text="Sẵn sàng.")
        stats = self.manifest_db.get_summary_stats()
        self._update_stats_display(stats)

    def _stop_action(self):
        """Requests graceful stop of automation loop."""
        self.automation.request_stop()
        self.lbl_status.config(text="Đang dừng sau hóa đơn hiện tại...")

    def _refresh_history_table(self):
        """Clears and re-populates treeview from database."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        history = self.manifest_db.get_all_history()
        for h in history[:100]:
            parts = h.get("khoa_hoa_don", "").split("_")
            mst = parts[0] if len(parts) > 0 else ""
            kh = parts[1] if len(parts) > 1 else ""
            sh = parts[2] if len(parts) > 2 else ""

            status = h.get("trang_thai", "")
            tag = "success" if status in ("XML_EXTRACTED", "EXPORTED") else "fail"
            self.tree.insert("", tk.END, values=(
                h.get("thoi_diem", ""),
                sh,
                kh,
                mst,
                status,
                h.get("ten_xml_dau_ra", ""),
                h.get("thong_bao_loi", ""),
            ), tags=(tag,))

    def _export_excel_action(self):
        """Exports all XMLs in ALLINVOICE and SQLite history to Excel."""
        try:
            self.lbl_status.config(text="Đang xuất báo cáo Excel...")
            output_file = export_from_allinvoice_folder(
                xml_dir=ALLINVOICE_DIR,
                output_path=DEFAULT_EXCEL_PATH,
                manifest_db=self.manifest_db
            )
            self.lbl_status.config(text=f"Đã xuất file Excel: {output_file.name}")
            if messagebox.askyesno("Thành công", f"Đã xuất thành công báo cáo Excel tại:\n{output_file}\n\nBạn có muốn mở file ngay bây giờ?"):
                self._open_excel_file()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xuất file Excel: {e}")
            self.lbl_status.config(text="Lỗi xuất Excel.")

    def _open_allinvoice_folder(self):
        if ALLINVOICE_DIR.exists():
            os.startfile(str(ALLINVOICE_DIR))
        else:
            messagebox.showinfo("Thông báo", "Thư mục ALLINVOICE chưa tồn tại.")

    def _open_excel_file(self):
        if DEFAULT_EXCEL_PATH.exists():
            os.startfile(str(DEFAULT_EXCEL_PATH))
        else:
            messagebox.showinfo("Thông báo", "Chưa có file Excel. Vui lòng bấm 'Xuất Excel Tổng Hợp' trước.")

    def _on_close(self):
        """Cleans up browser when closing desktop application."""
        if self.is_running:
            if not messagebox.askyesno("Thoát", "Tool đang trong quá trình tải hóa đơn. Bạn có chắc muốn dừng và thoát?"):
                return
            self.automation.request_stop()

        def _close_task():
            try:
                self.browser_manager.close()
            except Exception:
                pass

        self.browser_worker.submit(_close_task)
        self.browser_worker.stop()
        self.destroy()


def main():
    app = TaxInvoiceApp()
    app.mainloop()


if __name__ == "__main__":
    main()
