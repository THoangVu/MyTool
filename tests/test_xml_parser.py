"""Tests for xml_parser module."""

import unittest
from pathlib import Path

from src.tax_invoice_downloader.xml_parser import (
    parse_invoice_xml,
    generate_safe_xml_filename,
    XmlParsingError,
)
from src.tax_invoice_downloader.zip_xml_extractor import extract_invoice_xml_bytes


class TestXmlParser(unittest.TestCase):

    def setUp(self):
        self.sample_xml = """<?xml version="1.0" encoding="utf-8"?>
        <HDon>
            <DLHDon>
                <TTChung>
                    <KHMSHDon>1</KHMSHDon>
                    <KHHDon>C26TNT</KHHDon>
                    <SHDon>00005286</SHDon>
                    <NLap>2026-10-09</NLap>
                    <DVTTe>VND</DVTTe>
                    <HDCTTChinh>0</HDCTTChinh>
                </TTChung>
                <NDHDon>
                    <NBan>
                        <Ten>CÔNG TY TNHH NAM THẠNH</Ten>
                        <MST>3400401523</MST>
                        <DChi>82B Trưng Trắc, Phường Phan Thiết</DChi>
                    </NBan>
                    <NMua>
                        <Ten>HỘ KINH DOANH THỊNH ĐẠT</Ten>
                        <MST>060176009807</MST>
                    </NMua>
                    <DSHHDVu>
                        <HHDVu>
                            <STT>1</STT>
                            <MHHDVu>SP01</MHHDVu>
                            <THHDVu>Sản phẩm A</THHDVu>
                            <DVTinh>Cái</DVTinh>
                            <SLuong>5.0</SLuong>
                            <DGia>30555.56</DGia>
                            <ThTien>152778.0</ThTien>
                            <TSuat>8%</TSuat>
                            <TTKhac>
                                <TTin>
                                    <TTruong>VATAmount</TTruong>
                                    <DLieu>12222.0</DLieu>
                                </TTin>
                            </TTKhac>
                        </HHDVu>
                        <HHDVu>
                            <STT>2</STT>
                            <MHHDVu>KK0000</MHHDVu>
                            <THHDVu>Kim Kẹp Giấy</THHDVu>
                            <DVTinh>Hộp</DVTinh>
                            <SLuong>20</SLuong>
                            <DGia>2592.59</DGia>
                            <ThTien>51852.0</ThTien>
                            <TSuat>8%</TSuat>
                        </HHDVu>
                    </DSHHDVu>
                    <TToan>
                        <TgTCThue>204630.0</TgTCThue>
                        <TgTThue>16370.0</TgTThue>
                        <TTCKTMai>0.0</TTCKTMai>
                        <TgTTTBSo>221000.0</TgTTTBSo>
                    </TToan>
                </NDHDon>
            </DLHDon>
        </HDon>"""

    def test_parse_invoice_header(self):
        """Test extraction of header fields including leading zeros in invoice number."""
        header = parse_invoice_xml(self.sample_xml)
        self.assertEqual(header.mst_nguoi_ban, "3400401523")
        self.assertEqual(header.ten_nguoi_ban, "CÔNG TY TNHH NAM THẠNH")
        self.assertEqual(header.mst_nguoi_mua, "060176009807")
        self.assertEqual(header.kh_hoa_don, "C26TNT")
        self.assertEqual(header.sh_hoa_don, "00005286")  # Must NOT lose leading zeros
        self.assertEqual(header.ngay_lap, "2026-10-09")
        self.assertEqual(header.tien_chua_thue, 204630.0)
        self.assertEqual(header.tien_thue, 16370.0)
        self.assertEqual(header.tong_tien, 221000.0)

    def test_parse_product_rows(self):
        """Test extraction of line items."""
        header = parse_invoice_xml(self.sample_xml)
        self.assertEqual(len(header.items), 2)

        item1 = header.items[0]
        self.assertEqual(item1.ma_hang, "SP01")
        self.assertEqual(item1.ten_hang, "Sản phẩm A")
        self.assertEqual(item1.dvt, "Cái")
        self.assertEqual(item1.so_luong, 5.0)
        self.assertEqual(item1.don_gia, 30555.56)
        self.assertEqual(item1.thanh_tien, 152778.0)
        self.assertEqual(item1.thue_suat, "8%")
        self.assertEqual(item1.tien_thue, 12222.0)

        item2 = header.items[1]
        self.assertEqual(item2.ma_hang, "KK0000")
        self.assertEqual(item2.so_luong, 20.0)

    def test_xml_with_namespace(self):
        """Test parser correctly handles XML containing namespaces."""
        ns_xml = """<HDon xmlns="http://hoadondientu.gdt.gov.vn">
            <DLHDon>
                <TTChung>
                    <KHMSHDon>1</KHMSHDon>
                    <KHHDon>1C24TYY</KHHDon>
                    <SHDon>0000100</SHDon>
                    <NLap>2026-10-15</NLap>
                </TTChung>
                <NDHDon>
                    <NBan><MST>0100109106</MST><Ten>Viettel</Ten></NBan>
                    <NMua><MST>0300123456</MST></NMua>
                    <DSHHDVu />
                    <TToan><TgTTTBSo>500000</TgTTTBSo></TToan>
                </NDHDon>
            </DLHDon>
        </HDon>"""
        header = parse_invoice_xml(ns_xml)
        self.assertEqual(header.mst_nguoi_ban, "0100109106")
        self.assertEqual(header.kh_hoa_don, "1C24TYY")
        self.assertEqual(header.sh_hoa_don, "0000100")
        self.assertEqual(header.ngay_lap, "2026-10-15")

    def test_missing_mandatory_fields_raises_error(self):
        """Test XmlParsingError is raised when mandatory fields (e.g. MST or SHDon) are missing."""
        invalid_xml = "<HDon><DLHDon><TTChung><SHDon>123</SHDon></TTChung></DLHDon></HDon>"
        with self.assertRaises(XmlParsingError):
            parse_invoice_xml(invalid_xml)

    def test_generate_safe_xml_filename(self):
        """Test canonical filename generation."""
        filename = generate_safe_xml_filename("3400401523", "C26TNT", "00005286", "2026-10-09")
        self.assertEqual(filename, "3400401523_C26TNT_00005286_20261009.xml")

    def test_real_invoice_zip_xml(self):
        """Test parsing invoice.xml from real invoice.zip if present."""
        sample_zip = Path(r"c:\Users\user\Downloads\invoice.zip")
        if sample_zip.exists():
            xml_bytes = extract_invoice_xml_bytes(sample_zip)
            header = parse_invoice_xml(xml_bytes, source_filename="invoice.xml")
            self.assertEqual(header.mst_nguoi_ban, "3400401523")
            self.assertEqual(header.kh_hoa_don, "C26TNT")
            self.assertEqual(header.sh_hoa_don, "00005286")
            self.assertEqual(header.ngay_lap, "2026-10-09")
            self.assertEqual(len(header.items), 2)


if __name__ == "__main__":
    unittest.main()
