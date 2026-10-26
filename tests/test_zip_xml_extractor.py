"""Tests for zip_xml_extractor module."""

import io
import os
import zipfile
import unittest
from pathlib import Path

from src.tax_invoice_downloader.zip_xml_extractor import (
    extract_invoice_xml_bytes,
    extract_and_save_invoice_xml,
    ZipExtractionError,
)


class TestZipXmlExtractor(unittest.TestCase):

    def _create_mock_zip(self, files_dict: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in files_dict.items():
                zf.writestr(filename, content)
        return buf.getvalue()

    def test_extract_valid_zip_with_invoice_xml(self):
        """Test extraction succeeds when invoice.xml is present alongside other files."""
        mock_xml = b"<HDon><TTChung><SHDon>123</SHDon></TTChung></HDon>"
        zip_data = self._create_mock_zip({
            "details.js": "console.log('test');",
            "invoice.html": "<html><body>Invoice</body></html>",
            "invoice.xml": mock_xml,
            "sign-check.jpg": b"\xff\xd8\xff\xe0",
            "viewinvoice-bg.jpg": b"\xff\xd8\xff\xe0",
        })

        extracted = extract_invoice_xml_bytes(zip_data)
        self.assertEqual(extracted, mock_xml)

    def test_missing_invoice_xml(self):
        """Test ZipExtractionError is raised when invoice.xml is missing."""
        zip_data = self._create_mock_zip({
            "details.js": "console.log('test');",
            "invoice.html": "<html><body>Invoice</body></html>",
        })
        with self.assertRaises(ZipExtractionError) as ctx:
            extract_invoice_xml_bytes(zip_data)
        self.assertIn("Không tìm thấy file invoice.xml", str(ctx.exception))

    def test_duplicate_invoice_xml(self):
        """Test ZipExtractionError is raised when multiple invoice.xml files exist."""
        zip_data = self._create_mock_zip({
            "subfolder/invoice.xml": b"<xml>1</xml>",
            "invoice.xml": b"<xml>2</xml>",
        })
        with self.assertRaises(ZipExtractionError) as ctx:
            extract_invoice_xml_bytes(zip_data)
        self.assertIn("Phát hiện nhiều file invoice.xml", str(ctx.exception))

    def test_invalid_corrupted_zip(self):
        """Test ZipExtractionError is raised on corrupt or non-zip bytes."""
        corrupt_data = b"This is not a zip file at all"
        with self.assertRaises(ZipExtractionError) as ctx:
            extract_invoice_xml_bytes(corrupt_data)
        self.assertIn("không phải định dạng ZIP hợp lệ", str(ctx.exception))

    def test_extract_real_sample_zip_if_exists(self):
        """Test extraction with real sample invoice.zip from user's Downloads."""
        sample_path = Path(r"c:\Users\user\Downloads\invoice.zip")
        if sample_path.exists():
            extracted = extract_invoice_xml_bytes(sample_path)
            self.assertTrue(extracted.startswith(b"<HDon") or b"<DLHDon" in extracted)
            self.assertIn(b"3400401523", extracted)


if __name__ == "__main__":
    unittest.main()
