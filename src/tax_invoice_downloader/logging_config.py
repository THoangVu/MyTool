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
                    source_page INTEGER DEFAULT 1,
                    status TEXT,
                    retry_count INTEGER DEFAULT 0,
                    download_path TEXT,
                    downloaded_at TEXT,
                    file_size INTEGER DEFAULT 0,
                    sha256 TEXT,
                    last_error_code TEXT,
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
                    ma_loi TEXT DEFAULT '',
                    thong_bao_loi TEXT
                )
            """)

            # Safe migration for any missing columns
            existing_manifest_cols = [r["name"] for r in cursor.execute("PRAGMA table_info(invoice_manifest)").fetchall()]
            for col_def, col_name in [
                ("source_page INTEGER DEFAULT 1", "source_page"),
                ("download_path TEXT", "download_path"),
                ("downloaded_at TEXT", "downloaded_at"),
                ("file_size INTEGER DEFAULT 0", "file_size"),
                ("sha256 TEXT", "sha256"),
                ("last_error_code TEXT", "last_error_code"),
            ]:
                if col_name not in existing_manifest_cols:
                    try:
                        cursor.execute(f"ALTER TABLE invoice_manifest ADD COLUMN {col_def}")
                    except Exception:
                        pass

            existing_history_cols = [r["name"] for r in cursor.execute("PRAGMA table_info(download_history)").fetchall()]
            if "ma_loi" not in existing_history_cols:
                try:
                    cursor.execute("ALTER TABLE download_history ADD COLUMN ma_loi TEXT DEFAULT ''")
                except Exception:
                    pass

            conn.commit()

    def is_invoice_completed(
        self,
        invoice_key: str,
        sh_hoa_don: str = "",
        kh_hoa_don: str = "",
        allinvoice_dir: Optional[Path] = None,
    ) -> bool:
        """Checks if an invoice has already been successfully extracted and verified on disk."""
        valid_statuses = ("SUCCESS", "ALREADY_VERIFIED", "XML_EXTRACTED", "EXPORTED")
        found_record = None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if invoice_key:
                cursor.execute(
                    "SELECT invoice_key, xml_filename, status FROM invoice_manifest WHERE invoice_key = ?",
                    (invoice_key,)
                )
                r = cursor.fetchone()
                if r and r["status"] in valid_statuses:
                    found_record = dict(r)

            if not found_record and sh_hoa_don:
                clean_sh = "".join(c for c in sh_hoa_don if c.isdigit())
                clean_kh = "".join(c for c in kh_hoa_don if c.isalnum() or c in ("-", "_"))
                sh_lstrip = clean_sh.lstrip('0') or "0"
                sh_variants = [clean_sh, clean_sh.zfill(8), sh_lstrip]
                placeholders = ",".join("?" for _ in sh_variants)
                if clean_kh:
                    cursor.execute(
                        f"SELECT invoice_key, xml_filename, status FROM invoice_manifest "
                        f"WHERE (sh_hoa_don IN ({placeholders}) OR ltrim(sh_hoa_don, '0') = ?) "
                        f"AND (kh_hoa_don = ? OR kh_hoa_don LIKE ?)",
                        (*sh_variants, sh_lstrip, clean_kh, f"%{clean_kh}%")
                    )
                    r = cursor.fetchone()
                    if r and r["status"] in valid_statuses:
                        found_record = dict(r)
                else:
                    cursor.execute(
                        f"SELECT invoice_key, xml_filename, status FROM invoice_manifest "
                        f"WHERE (sh_hoa_don IN ({placeholders}) OR ltrim(sh_hoa_don, '0') = ?)",
                        (*sh_variants, sh_lstrip)
                    )
                    r = cursor.fetchone()
                    if r and r["status"] in valid_statuses:
                        found_record = dict(r)

        if not found_record:
            return False

        # Physical file verification: check that XML file actually exists and is non-empty
        if allinvoice_dir is not None:
            xml_name = found_record.get("xml_filename")
            if xml_name:
                xml_path = Path(allinvoice_dir) / xml_name
                if not (xml_path.is_file() and xml_path.stat().st_size > 0):
                    return False
            else:
                return False

        return True

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
        source_page: int = 1,
        status: str = "PENDING",
        error_message: str = "",
        last_error_code: str = "",
        download_path: str = "",
        file_size: int = 0,
        sha256: str = "",
        increment_retry: bool = False,
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        downloaded_at = now if status in ("SUCCESS", "ALREADY_VERIFIED", "XML_EXTRACTED") else ""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count, download_path, sha256 FROM invoice_manifest WHERE invoice_key = ?", (invoice_key,))
            row = cursor.fetchone()
            retry_count = 0
            if row:
                retry_count = row["retry_count"] or 0
                if increment_retry:
                    retry_count += 1
                cursor.execute("""
                    UPDATE invoice_manifest
                    SET mst_nguoi_ban = coalesce(nullif(?, ''), mst_nguoi_ban),
                        kh_hoa_don = coalesce(nullif(?, ''), kh_hoa_don),
                        sh_hoa_don = coalesce(nullif(?, ''), sh_hoa_don),
                        ngay_lap = coalesce(nullif(?, ''), ngay_lap),
                        xml_filename = coalesce(nullif(?, ''), xml_filename),
                        source_page = coalesce(nullif(?, 0), source_page),
                        status = ?,
                        retry_count = ?,
                        download_path = coalesce(nullif(?, ''), download_path),
                        downloaded_at = coalesce(nullif(?, ''), downloaded_at),
                        file_size = coalesce(nullif(?, 0), file_size),
                        sha256 = coalesce(nullif(?, ''), sha256),
                        last_error_code = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE invoice_key = ?
                """, (
                    mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename,
                    source_page, status, retry_count, download_path, downloaded_at,
                    file_size, sha256, last_error_code, error_message, now, invoice_key
                ))
            else:
                if increment_retry:
                    retry_count = 1
                cursor.execute("""
                    INSERT INTO invoice_manifest
                    (invoice_key, mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename, source_page, status, retry_count, download_path, downloaded_at, file_size, sha256, last_error_code, error_message, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice_key, mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap, xml_filename,
                    source_page, status, retry_count, download_path, downloaded_at, file_size, sha256,
                    last_error_code, error_message, now, now
                ))
            conn.commit()

    def record_history(self, record: DownloadHistoryRecord):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            ma_loi = getattr(record, "ma_loi", "")
            cursor.execute("""
                INSERT INTO download_history
                (thoi_diem, khoa_hoa_don, trang_thai, so_lan_thu, ten_zip_tam, ten_xml_dau_ra, ma_loi, thong_bao_loi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.thoi_diem,
                record.khoa_hoa_don,
                record.trang_thai,
                record.so_lan_thu,
                record.ten_zip_tam,
                record.ten_xml_dau_ra,
                ma_loi,
                record.thong_bao_loi,
            ))
            conn.commit()

    def get_all_manifest_records(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM invoice_manifest ORDER BY rowid ASC")
            return [dict(r) for r in cursor.fetchall()]

    def get_missing_or_failed_manifest(self) -> List[Dict[str, Any]]:
        """Returns list of invoices that failed or are pending."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM invoice_manifest WHERE status IN ('FAILED', 'PENDING', 'IN_PROGRESS') ORDER BY rowid ASC"
            )
            return [dict(r) for r in cursor.fetchall()]

    def export_missing_or_failed_csv(self, output_csv_path: Path) -> int:
        """Exports missing_or_failed_invoices.csv as required by Section 6."""
        import csv
        items = self.get_missing_or_failed_manifest()
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "khoa_hoa_don",
                "mst_nguoi_ban",
                "kh_hoa_don",
                "sh_hoa_don",
                "ngay_lap",
                "trang_thai_cuoi",
                "so_lan_thu",
                "ma_loi_cuoi",
                "thong_bao_loi_cuoi",
            ])
            for item in items:
                writer.writerow([
                    item.get("invoice_key", ""),
                    item.get("mst_nguoi_ban", ""),
                    item.get("kh_hoa_don", ""),
                    item.get("sh_hoa_don", ""),
                    item.get("ngay_lap", ""),
                    item.get("status", ""),
                    item.get("retry_count", 0),
                    item.get("last_error_code", ""),
                    item.get("error_message", ""),
                ])
        return len(items)

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
            success = counts.get("SUCCESS", 0) + counts.get("XML_EXTRACTED", 0) + counts.get("EXPORTED", 0)
            already_verified = counts.get("ALREADY_VERIFIED", 0)
            errors = counts.get("FAILED", 0)
            pending = counts.get("PENDING", 0) + counts.get("IN_PROGRESS", 0)
            skipped = counts.get("SKIPPED", 0) + already_verified
            downloaded = success + counts.get("DOWNLOADED", 0)
            missing = errors + pending

            from .models import ReconciliationReport
            recon = ReconciliationReport(
                source_count=total,
                success_count=success,
                already_verified_count=already_verified,
                failed_count=errors,
                pending_count=pending,
                duplicate_file_count=0,
                missing_invoice_count=missing,
            )
            recon.verify_balance()

            return SummaryStats(
                so_dong_tim_thay=total,
                so_da_tai=downloaded,
                so_xml_thanh_cong=success,
                so_loi=errors,
                so_bo_qua=skipped,
                so_cho_xu_ly=pending,
                so_thieu=missing,
                reconciliation=recon,
            )
