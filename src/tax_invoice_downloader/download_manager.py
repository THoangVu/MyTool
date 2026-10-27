"""Download manager for managing temporary ZIPs, extracting invoice.xml, saving to ALLINVOICE, and logging progress."""

import os
import shutil
import zipfile
import hashlib
import time
from pathlib import Path
from typing import Optional, Tuple, Union

from .models import InvoiceKey, InvoiceHeader, DownloadHistoryRecord
from .zip_xml_extractor import extract_invoice_xml_bytes, ZipExtractionError
from .xml_parser import parse_invoice_xml, XmlParsingError
from .logging_config import setup_logger, ManifestDB

logger = setup_logger("download_manager")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALLINVOICE_DIR = BASE_DIR / "ALLINVOICE"
DOWNLOADS_DIR = BASE_DIR / "downloads"


class DownloadManagerError(Exception):
    """Custom exception raised when download processing fails."""
    def __init__(self, message: str, error_code: str = "DOWNLOAD_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class DownloadManager:
    """Handles verification and extraction of downloaded ZIP files, saving XML to ALLINVOICE, and state persistence."""

    def __init__(
        self,
        downloads_dir: Optional[Path] = None,
        allinvoice_dir: Optional[Path] = None,
        manifest_db: Optional[ManifestDB] = None,
        clean_temp_zips: bool = True,
    ):
        self.downloads_dir = downloads_dir or DOWNLOADS_DIR
        self.allinvoice_dir = allinvoice_dir or ALLINVOICE_DIR
        self.manifest_db = manifest_db or ManifestDB()
        self.clean_temp_zips = clean_temp_zips

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.allinvoice_dir.mkdir(parents=True, exist_ok=True)

    def create_isolated_temp_dir(self, invoice_key: str) -> Path:
        """Tạo thư mục tạm riêng biệt cho từng hóa đơn theo Mục 3 Bước C."""
        safe_key = "".join(c for c in invoice_key if c.isalnum() or c in ("-", "_"))
        unique_name = f"tmp_{safe_key}_{time.time_ns()}"
        temp_dir = self.downloads_dir / unique_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def wait_for_download_stabilization(self, folder: Path, timeout: float = 30.0) -> Path:
        """Chờ file trong thư mục hoàn tất tải xuống, không còn file tạm (.crdownload, .part, .tmp)
        và kích thước file ổn định qua 2 lần kiểm tra liên tiếp.
        """
        start = time.time()
        found_target: Optional[Path] = None

        while time.time() - start < timeout:
            all_files = [f for f in folder.iterdir() if f.is_file()]
            # Kiểm tra xem có file tải dở không
            incomplete = [f for f in all_files if f.suffix.lower() in (".crdownload", ".part", ".tmp")]
            if incomplete:
                time.sleep(0.3)
                continue

            # Tìm file zip hoặc xml
            completed = [f for f in all_files if f.suffix.lower() in (".zip", ".xml", ".xlsx", ".xls")]
            if completed:
                cand = completed[0]
                size1 = cand.stat().st_size
                if size1 > 0:
                    time.sleep(0.3)
                    size2 = cand.stat().st_size
                    if size1 == size2:
                        found_target = cand
                        break
            time.sleep(0.2)

        if not found_target:
            raise DownloadManagerError(
                f"Quá thời gian ({timeout}s) chờ file tải hoàn tất hoặc file không xuất hiện.",
                error_code="TIMEOUT_DOWNLOAD"
            )
        return found_target

    def process_downloaded_zip(
        self,
        zip_path: Union[str, Path],
        expected_key: Optional[InvoiceKey] = None,
        source_page: int = 1,
        retry_count: int = 0,
    ) -> Tuple[Path, InvoiceHeader]:
        """Processes a downloaded ZIP file.

        1. Validates ZIP integrity.
        2. Extracts invoice.xml bytes safely in memory.
        3. Parses XML into InvoiceHeader.
        4. Matches against expected_key if provided.
        5. Computes SHA-256.
        6. Saves XML to ALLINVOICE/ using standard naming convention.
        7. Updates SQLite manifest and history.
        8. Cleans up temporary files.
        """
        zip_file = Path(zip_path)
        if not zip_file.is_file():
            err = f"File tải về không tồn tại: {zip_file}"
            self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="FILE_NOT_FOUND", source_page=source_page)
            raise DownloadManagerError(err, error_code="FILE_NOT_FOUND")

        if zip_file.stat().st_size == 0:
            err = f"File tải về rỗng (0 bytes): {zip_file.name}"
            self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="FILE_EMPTY", source_page=source_page)
            raise DownloadManagerError(err, error_code="FILE_EMPTY")

        if zip_file.suffix.lower() in (".xlsx", ".xls"):
            err = f"Cổng Thuế trả về file Excel ({zip_file.name}) thay vì ZIP/XML hóa đơn"
            self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="EXCEL_RETURNED", source_page=source_page)
            raise DownloadManagerError(err, error_code="EXCEL_RETURNED")

        if zip_file.suffix.lower() == ".xml":
            try:
                xml_bytes = zip_file.read_bytes()
            except Exception as e:
                err = f"Lỗi đọc file XML ({zip_file.name}): {e}"
                self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="CORRUPT_XML", source_page=source_page)
                raise DownloadManagerError(err, error_code="CORRUPT_XML") from e
        else:
            if not zipfile.is_zipfile(zip_file):
                err = f"File tải về không phải ZIP hoặc XML hợp lệ hoặc bị lỗi: {zip_file.name}"
                self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="CORRUPT_ZIP", source_page=source_page)
                raise DownloadManagerError(err, error_code="CORRUPT_ZIP")

            # Validate ZIP CRC integrity
            try:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        err = f"File ZIP bị lỗi CRC tại file con: {bad_file}"
                        self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="CORRUPT_ZIP", source_page=source_page)
                        raise DownloadManagerError(err, error_code="CORRUPT_ZIP")
            except zipfile.BadZipFile as e:
                err = f"File ZIP hỏng hoặc tải chưa xong: {e}"
                self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="CORRUPT_ZIP", source_page=source_page)
                raise DownloadManagerError(err, error_code="CORRUPT_ZIP") from e

            # Extract invoice.xml bytes
            try:
                xml_bytes = extract_invoice_xml_bytes(zip_file)
            except ZipExtractionError as e:
                err = f"Lỗi giải nén ZIP ({zip_file.name}): {e}"
                self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="NO_XML_IN_ZIP", source_page=source_page)
                raise DownloadManagerError(err, error_code="NO_XML_IN_ZIP") from e

        # Parse XML
        try:
            invoice_header = parse_invoice_xml(xml_bytes, source_filename=zip_file.name)
        except XmlParsingError as e:
            err = f"Lỗi đọc nội dung XML từ ZIP ({zip_file.name}): {e}"
            self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="CORRUPT_XML", source_page=source_page)
            raise DownloadManagerError(err, error_code="CORRUPT_XML") from e

        # Cross-check with expected row data if provided
        if expected_key:
            if expected_key.mst_nguoi_ban and expected_key.mst_nguoi_ban != invoice_header.mst_nguoi_ban:
                logger.warning(
                    f"MST người bán không khớp: dự kiến {expected_key.mst_nguoi_ban}, XML có {invoice_header.mst_nguoi_ban}"
                )
            if expected_key.sh_hoa_don:
                clean_exp_sh = "".join(c for c in expected_key.sh_hoa_don if c.isdigit()).lstrip("0")
                clean_act_sh = "".join(c for c in invoice_header.sh_hoa_don if c.isdigit()).lstrip("0")
                if clean_exp_sh and clean_act_sh and clean_exp_sh != clean_act_sh:
                    err = f"Số hóa đơn không khớp: dự kiến {expected_key.sh_hoa_don}, XML có {invoice_header.sh_hoa_don}"
                    self._record_failure(expected_key, err, zip_file.name, retry_count, error_code="DATA_MISMATCH", source_page=source_page)
                    raise DownloadManagerError(err, error_code="DATA_MISMATCH")

        # Compute SHA-256
        sha256_hash = hashlib.sha256(xml_bytes).hexdigest()

        # Standard filename: {MST}_{KYHIEU}_{SHDON}_{NGAYLAP}.xml
        base_xml_name = invoice_header.invoice_key.to_xml_filename()
        target_xml_path = self.allinvoice_dir / base_xml_name

        # Safe collision handling (Mục 7)
        if target_xml_path.exists():
            existing_bytes = target_xml_path.read_bytes()
            if existing_bytes == xml_bytes:
                logger.info(f"File XML {base_xml_name} đã tồn tại và giống hệt nội dung (SHA-256 trùng khớp).")
            else:
                # Same name but different content -> safe suffix, keep both
                counter = 1
                stem = target_xml_path.stem
                while target_xml_path.exists():
                    target_xml_path = self.allinvoice_dir / f"{stem}_{counter}.xml"
                    counter += 1
                logger.warning(f"File XML trùng tên nhưng khác nội dung! Đã đổi tên thành: {target_xml_path.name}")

        # Save XML to ALLINVOICE
        target_xml_path.write_bytes(xml_bytes)
        invoice_header.file_xml = target_xml_path.name
        invoice_header.trang_thai_trich_xuat = "THANH_CONG"

        # Update line items with target XML name
        for item in invoice_header.items:
            item.file_xml_nguon = target_xml_path.name

        # Update SQLite manifest
        inv_key_str = invoice_header.invoice_key.normalized_key()
        self.manifest_db.upsert_manifest(
            invoice_key=inv_key_str,
            mst_nguoi_ban=invoice_header.mst_nguoi_ban,
            kh_hoa_don=invoice_header.kh_hoa_don,
            sh_hoa_don=invoice_header.sh_hoa_don,
            ngay_lap=invoice_header.ngay_lap,
            xml_filename=target_xml_path.name,
            source_page=source_page,
            status="SUCCESS",
            error_message="",
            last_error_code="",
            download_path=str(target_xml_path),
            file_size=len(xml_bytes),
            sha256=sha256_hash,
        )

        # Record successful history
        self.manifest_db.record_history(DownloadHistoryRecord(
            khoa_hoa_don=inv_key_str,
            trang_thai="SUCCESS",
            so_lan_thu=retry_count,
            ten_zip_tam=zip_file.name,
            ten_xml_dau_ra=target_xml_path.name,
            ma_loi="",
            thong_bao_loi="",
        ))

        # Cleanup temporary ZIP if configured
        if self.clean_temp_zips:
            try:
                zip_file.unlink()
                # If zip was in an isolated temp folder, delete folder
                parent_dir = zip_file.parent
                if parent_dir != self.downloads_dir and parent_dir.name.startswith("tmp_"):
                    shutil.rmtree(parent_dir, ignore_errors=True)
                logger.debug(f"Đã dọn dẹp file ZIP tạm: {zip_file.name}")
            except Exception as e:
                logger.warning(f"Không thể xóa file ZIP tạm {zip_file.name}: {e}")

        logger.info(f"Đã lưu thành công hóa đơn: {target_xml_path.name} (SHA-256: {sha256_hash[:10]}...)")
        return target_xml_path, invoice_header

    def _record_failure(
        self,
        expected_key: Optional[InvoiceKey],
        error_msg: str,
        temp_zip_name: str,
        retry_count: int,
        error_code: str = "FAILED",
        source_page: int = 1,
    ):
        key_str = expected_key.normalized_key() if expected_key else "UNKNOWN"
        logger.error(f"[{error_code}] {error_msg}")
        self.manifest_db.upsert_manifest(
            invoice_key=key_str,
            mst_nguoi_ban=expected_key.mst_nguoi_ban if expected_key else "",
            kh_hoa_don=expected_key.kh_hoa_don if expected_key else "",
            sh_hoa_don=expected_key.sh_hoa_don if expected_key else "",
            ngay_lap=expected_key.ngay_lap if expected_key else "",
            source_page=source_page,
            status="FAILED",
            error_message=error_msg,
            last_error_code=error_code,
            increment_retry=True,
        )
        self.manifest_db.record_history(DownloadHistoryRecord(
            khoa_hoa_don=key_str,
            trang_thai="FAILED",
            so_lan_thu=retry_count,
            ten_zip_tam=temp_zip_name,
            ten_xml_dau_ra="",
            ma_loi=error_code,
            thong_bao_loi=error_msg,
        ))
