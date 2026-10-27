"""Unit tests for FIX_TAI_THIEU_XML_TU_DONG.md requirements."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.tax_invoice_downloader.models import InvoiceKey, ReconciliationReport, SummaryStats
from src.tax_invoice_downloader.logging_config import ManifestDB
from src.tax_invoice_downloader.download_manager import DownloadManager, DownloadManagerError
from src.tax_invoice_downloader.tax_portal import TaxPortalAutomation


class TestFixTaiThieuXml(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.downloads_dir = self.temp_dir / "downloads"
        self.allinvoice_dir = self.temp_dir / "ALLINVOICE"
        self.db_path = self.temp_dir / "test_manifest.db"

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.allinvoice_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_db = ManifestDB(db_path=self.db_path)
        self.dm = DownloadManager(
            downloads_dir=self.downloads_dir,
            allinvoice_dir=self.allinvoice_dir,
            manifest_db=self.manifest_db,
            clean_temp_zips=True,
        )
        self.automation = TaxPortalAutomation(download_manager=self.dm)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_announced_total_extraction(self):
        """Test extraction of announced count like 'Có 1.367 kết quả'."""
        page = MagicMock()
        mock_loc = MagicMock()
        mock_loc.count.return_value = 1
        mock_item = MagicMock()
        mock_item.inner_text.return_value = " Có 1.367 kết quả "
        mock_loc.nth.return_value = mock_item
        page.locator.return_value = mock_loc

        total = self.automation.get_announced_total_results(page)
        self.assertEqual(total, 1367)

    def test_reconciliation_formula_balanced(self):
        """Formula: source_count == success + already_verified + failed + pending."""
        report = ReconciliationReport(
            source_count=1367,
            success_count=1355,
            already_verified_count=0,
            failed_count=10,
            pending_count=2,
        )
        self.assertTrue(report.verify_balance())
        self.assertEqual(report.missing_invoice_count, 12)

    def test_reconciliation_formula_unbalanced_detected(self):
        """Formula detects unbalanced counts."""
        report = ReconciliationReport(
            source_count=1367,
            success_count=1350,
            already_verified_count=0,
            failed_count=10,
            pending_count=0,
        )
        # 1350 + 10 != 1367
        self.assertFalse(report.verify_balance())
        self.assertEqual(report.missing_invoice_count, 17)

    def test_missing_or_failed_csv_export(self):
        """Test generating missing_or_failed_invoices.csv with proper fields."""
        # Insert 1 success and 2 failed
        self.manifest_db.upsert_manifest(
            invoice_key="MST1_C26_00000001_20261001",
            mst_nguoi_ban="MST1",
            kh_hoa_don="C26",
            sh_hoa_don="00000001",
            ngay_lap="01/10/2026",
            status="SUCCESS",
        )
        self.manifest_db.upsert_manifest(
            invoice_key="MST2_C26_00000002_20261002",
            mst_nguoi_ban="MST2",
            kh_hoa_don="C26",
            sh_hoa_don="00000002",
            ngay_lap="02/10/2026",
            status="FAILED",
            last_error_code="TIMEOUT_BUTTON",
            error_message="Nút Xuất xml chưa sẵn sàng",
            increment_retry=True,
        )
        self.manifest_db.upsert_manifest(
            invoice_key="MST3_C26_00000003_20261003",
            mst_nguoi_ban="MST3",
            kh_hoa_don="C26",
            sh_hoa_don="00000003",
            ngay_lap="03/10/2026",
            status="PENDING",
        )

        csv_path = self.temp_dir / "missing_or_failed_invoices.csv"
        cnt = self.manifest_db.export_missing_or_failed_csv(csv_path)
        self.assertEqual(cnt, 2)
        self.assertTrue(csv_path.exists())

        content = csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("MST2_C26_00000002_20261002", content)
        self.assertIn("MST3_C26_00000003_20261003", content)
        self.assertNotIn("MST1_C26_00000001_20261001", content)
        self.assertIn("TIMEOUT_BUTTON", content)

    def test_isolated_temp_dir_creation(self):
        """Test each download gets an isolated temp folder."""
        d1 = self.dm.create_isolated_temp_dir("KEY1")
        d2 = self.dm.create_isolated_temp_dir("KEY1")
        self.assertTrue(d1.exists())
        self.assertTrue(d2.exists())
        self.assertNotEqual(d1, d2)

    def test_already_verified_check_with_disk_validation(self):
        """Test is_invoice_completed verifies both status and actual file on disk."""
        key = "3400401523_C26TNT_00005286_20261009"
        filename = "3400401523_C26TNT_00005286_20261009.xml"

        self.manifest_db.upsert_manifest(
            invoice_key=key,
            xml_filename=filename,
            status="SUCCESS",
        )

        # File does not exist yet on disk
        self.assertFalse(self.manifest_db.is_invoice_completed(key, allinvoice_dir=self.allinvoice_dir))

        # Create file on disk
        target_file = self.allinvoice_dir / filename
        target_file.write_bytes(b"<xml>valid</xml>")

        # Now it is verified!
        self.assertTrue(self.manifest_db.is_invoice_completed(key, allinvoice_dir=self.allinvoice_dir))


if __name__ == "__main__":
    unittest.main()
