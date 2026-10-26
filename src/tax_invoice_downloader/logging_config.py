"""Logging configuration and SQLite manifest for state persistence."""

import os
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime

from .models import DownloadHistoryRecord, SummaryStats

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = LOGS_DIR / "manifest.db"


def setup_logger(name: str = "tax_invoice_downloader", log_level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a logger that outputs to console and logs/app.log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        log_file = LOGS_DIR / "app.log"
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


class ManifestDB:
    """SQLite database to track invoice download states, avoiding duplicate downloads and enabling resume."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoice_manifest (
                    invoice_key TEXT PRIMARY KEY,
                    mst_nguoi_ban TEXT,
                    kh_hoa_don TEXT,
                    sh_hoa_don TEXT,
                    ngay_lap TEXT,
                    xml_filename TEXT,
                    status TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thoi_diem TEXT,
                    khoa_hoa_don TEXT,
                    trang_thai TEXT,
                    so_lan_thu INTEGER DEFAULT 0,
                    ten_zip_tam TEXT,
                    ten_xml_dau_ra TEXT,
                    thong_bao_loi TEXT
                )
            """)
            conn.commit()

    def is_invoice_completed(self, invoice_key: str, sh_hoa_don: str = "", kh_hoa_don: str = "") -> bool:
        """Checks if an invoice has already been successfully extracted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if invoice_key:
                cursor.execute(
                    "SELECT status FROM invoice_manifest WHERE invoice_key = ? AND status IN ('XML_EXTRACTED', 'EXPORTED')",
                    (invoice_key,)
                )
                if cursor.fetchone():
                    return True
            if sh_hoa_don:
                clean_sh = "".join(c for c in sh_hoa_don if c.isdigit())
                clean_kh = "".join(c for c in kh_hoa_don if c.isalnum() or c in ("-", "_"))
                if clean_kh:
                    cursor.execute(
                        "SELECT status FROM invoice_manifest WHERE (sh_hoa_don = ? OR sh_hoa_don = ?) AND kh_hoa_don = ? AND status IN ('XML_EXTRACTED', 'EXPORTED')",
                        (clean_sh, clean_sh.zfill(8), clean_kh)
                    )
                    if cursor.fetchone():
                        return True
        return False

    def get_invoice_status(self, invoice_key: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM invoice_manifest WHERE invoice_key = ?", (invoice_key,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_manifest(
        self,
        invoice_key: str,
        mst_nguoi_ban: str = "",
        kh_hoa_don: str = "",
        sh_hoa_don: str = "",
        ngay_lap: str = "",
        xml_filename: str = "",
        status: str = "PENDING",
        error_message: str = "",
        increment_retry: bool = False,
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count FROM invoice_manifest WHERE invoice_key = ?", (invoice_key,))
            row = cursor.fetchone()
            retry_count = 0
            if row:
                retry_count = row["retry_count"]
                if increment_retry:
                    retry_count += 1
                cursor.execute("""
                    UPDATE invoice_manifest
                    SET mst_nguoi_ban = coalesce(nullif(?, ''), mst_nguoi_ban),
                        kh_hoa_don = coalesce(nullif(?, ''), kh_hoa_don),
                        sh_hoa_don = coalesce(nullif(?, ''), sh_hoa_don),
                        ngay_lap = coalesce(nullif(?, ''), ngay_lap),
                        xml_filename = coalesce(nullif(?, ''), xml_filename),
                        status = ?,
                        retry_count = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE invoice_key = ?
                """, (mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename, status, retry_count, error_message, now, invoice_key))
            else:
                if increment_retry:
                    retry_count = 1
                cursor.execute("""
                    INSERT INTO invoice_manifest
                    (invoice_key, mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename, status, retry_count, error_message, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (invoice_key, mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename, status, retry_count, error_message, now, now))
            conn.commit()

    def record_history(self, record: DownloadHistoryRecord):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO download_history
                (thoi_diem, khoa_hoa_don, trang_thai, so_lan_thu, ten_zip_tam, ten_xml_dau_ra, thong_bao_loi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record.thoi_diem,
                record.khoa_hoa_don,
                record.trang_thai,
                record.so_lan_thu,
                record.ten_zip_tam,
                record.ten_xml_dau_ra,
                record.thong_bao_loi,
            ))
            conn.commit()

    def get_all_history(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM download_history ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    def get_summary_stats(self) -> SummaryStats:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, count(*) as cnt FROM invoice_manifest GROUP BY status")
            counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}
            total = sum(counts.values())
            success = counts.get("XML_EXTRACTED", 0) + counts.get("EXPORTED", 0)
            errors = counts.get("FAILED", 0)
            skipped = counts.get("SKIPPED", 0)
            downloaded = success + counts.get("DOWNLOADED", 0)
            return SummaryStats(
                so_dong_tim_thay=total,
                so_da_tai=downloaded,
                so_xml_thanh_cong=success,
                so_loi=errors,
                so_bo_qua=skipped,
            )
