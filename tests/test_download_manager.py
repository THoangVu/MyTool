"""Tests for download_manager module."""

import io
import shutil
import zipfile
import unittest
from pathlib import Path

from src.tax_invoice_downloader.download_manager import DownloadManager, DownloadManagerError
from src.tax_invoice_downloader.logging_config import ManifestDB
from src.tax_invoice_downloader.models import InvoiceKey


class TestDownloadManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(__file__).resolve().parent / "test_env"
        self.downloads_dir = self.test_dir / "downloads"
        self.allinvoice_dir = self.test_dir / "ALLINVOICE"
        self.manifest_db_path = self.test_dir / "manifest.db"

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.allinvoice_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_db = ManifestDB(db_path=self.manifest_db_path)
        self.dm = DownloadManager(
            downloads_dir=self.downloads_dir,
            allinvoice_dir=self.allinvoice_dir,
            manifest_db=self.manifest_db,
            clean_temp_zips=True,
        )

        self.sample_xml = b"""<?xml version="1.0" encoding="utf-8"?>
        <HDon>
            <DLHDon>
                <TTChung>
                    <KHMSHDon>1</KHMSHDon>
                    <KHHDon>C26TNT</KHHDon>
                    <SHDon>00005286</SHDon>
                    <NLap>2026-10-09</NLap>
                    <DVTTe>VND</DVTTe>
                </TTChung>
                <NDHDon>
                    <NBan><MST>3400401523</MST><Ten>CONG TY NAM THANH</Ten></NBan>
                    <NMua><MST>060176009807</MST><Ten>HO KINH DOANH THINH DAT</Ten></NMua>
                    <DSHHDVu>
                        <HHDVu>
                            <STT>1</STT>
                            <MHHDVu>SP01</MHHDVu>
                            <THHDVu>Hang hoa</THHDVu>
                            <DVTinh>Cai</DVTinh>
                            <SLuong>1</SLuong>
                            <DGia>10000</DGia>
                            <ThTien>10000</ThTien>
                            <TSuat>10%</TSuat>
                        </HHDVu>
                    </DSHHDVu>
                    <TToan><TgTTTBSo>11000</TgTTTBSo></TToan>
                </NDHDon>
            </DLHDon>
        </HDon>"""

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_zip(self, name: str, files: dict) -> Path:
        zip_path = self.downloads_dir / name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, content in files.items():
                zf.writestr(fname, content)
        return zip_path

    def test_process_valid_download(self):
        """Test processing a downloaded ZIP extracts XML and saves to ALLINVOICE."""
        zip_file = self._create_zip("invoice_temp.zip", {
            "details.js": "alert('ignore');",
            "invoice.html": "<html><body>ignore</body></html>",
            "invoice.xml": self.sample_xml,
            "sign-check.jpg": b"\x00\x00",
        })

        expected_key = InvoiceKey("3400401523", "C26TNT", "00005286", "2026-10-09")
        xml_path, header = self.dm.process_downloaded_zip(zip_file, expected_key=expected_key)

        self.assertTrue(xml_path.exists())
        self.assertEqual(xml_path.name, "3400401523_C26TNT_00005286_20261009.xml")
        self.assertEqual(header.sh_hoa_don, "00005286")

        # Verify ZIP was cleaned up
        self.assertFalse(zip_file.exists())

        # Verify Manifest DB recorded the invoice
        inv_status = self.manifest_db.get_invoice_status(expected_key.normalized_key())
        self.assertIsNotNone(inv_status)
        self.assertIn(inv_status["status"], ("SUCCESS", "XML_EXTRACTED"))
        self.assertEqual(inv_status["xml_filename"], "3400401523_C26TNT_00005286_20261009.xml")

    def test_corrupted_zip_records_failure(self):
        """Test corrupted ZIP raises error and records failure in manifest."""
        corrupt_zip = self.downloads_dir / "corrupt.zip"
        corrupt_zip.write_bytes(b"not a valid zip content")

        expected_key = InvoiceKey("3400401523", "C26TNT", "00009999", "2026-10-09")
        with self.assertRaises(DownloadManagerError):
            self.dm.process_downloaded_zip(corrupt_zip, expected_key=expected_key)

        inv_status = self.manifest_db.get_invoice_status(expected_key.normalized_key())
        self.assertIsNotNone(inv_status)
        self.assertEqual(inv_status["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
