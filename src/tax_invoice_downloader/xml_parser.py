"""Parser for Vietnamese electronic invoice XML (Circular 78 / Decree 123 & related formats)."""

import re
import os
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple
import xml.etree.ElementTree as ET

from .models import InvoiceHeader, InvoiceLineItem, InvoiceKey


class XmlParsingError(Exception):
    """Custom exception raised when XML parsing or validation fails."""
    pass


def _clean_str(val: Optional[str]) -> str:
    """Trim whitespace and return clean string, or empty string if None."""
    if val is None:
        return ""
    return str(val).strip()


def _parse_number(val: Any) -> Optional[float]:
    """Safely parse numbers from XML strings preserving precision and handling formatting."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # If string contains comma as decimal separator without period (e.g. 1234,56)
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "," in s and "." in s:
        # e.g., 1,234.56 -> remove comma
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            # e.g. 1.234,56 -> remove period, replace comma with period
            s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _find_elem(root: ET.Element, *tags: str) -> Optional[ET.Element]:
    """Find first element matching any of the given tag names (ignoring namespace and case)."""
    tag_set = {t.lower() for t in tags}
    for elem in root.iter():
        clean_tag = elem.tag.split("}")[-1].lower()
        if clean_tag in tag_set:
            return elem
    return None


def _get_text(root: Optional[ET.Element], *tags: str, default: str = "") -> str:
    """Finds element and returns stripped text."""
    if root is None:
        return default
    elem = _find_elem(root, *tags)
    if elem is not None and elem.text:
        return elem.text.strip()
    return default


def _format_date(date_str: str) -> str:
    """Normalizes date string to YYYY-MM-DD."""
    s = _clean_str(date_str)
    # Check YYYY-MM-DD
    m1 = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m1:
        return f"{m1.group(1)}-{int(m1.group(2)):02d}-{int(m1.group(3)):02d}"
    # Check DD/MM/YYYY
    m2 = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m2:
        return f"{m2.group(3)}-{int(m2.group(2)):02d}-{int(m2.group(1)):02d}"
    return s


def parse_invoice_xml(xml_content: Union[str, bytes, Path], source_filename: str = "") -> InvoiceHeader:
    """Parses invoice XML content into an InvoiceHeader with its line items.

    Validates required fields:
    - MST người bán (Seller tax code)
    - Ký hiệu hóa đơn (Invoice symbol)
    - Số hóa đơn (Invoice number, kept as string with leading zeros)
    - Ngày lập (Invoice date)
    """
    if isinstance(xml_content, Path):
        source_filename = source_filename or xml_content.name
        xml_bytes = xml_content.read_bytes()
    elif isinstance(xml_content, str):
        if os.path.exists(xml_content):
            source_filename = source_filename or Path(xml_content).name
            xml_bytes = Path(xml_content).read_bytes()
        else:
            xml_bytes = xml_content.encode("utf-8")
    elif isinstance(xml_content, bytes):
        xml_bytes = xml_content
    else:
        raise XmlParsingError("Nguồn XML không hợp lệ")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise XmlParsingError(f"Cú pháp XML không hợp lệ: {e}") from e

    # Find TTChung (General Info)
    tt_chung = _find_elem(root, "TTChung", "GeneralInvoiceInfo")

    # TTChung
    tt_chung_node = tt_chung if tt_chung is not None else root
    # Ký hiệu mẫu số (KHMSHDon / InvoiceTemplateCode)
    kh_mau_so = _get_text(tt_chung_node, "KHMSHDon", "InvoiceTemplateCode", "MauSo")
    # Ký hiệu hóa đơn (KHHDon / InvoiceSeries)
    kh_hoa_don = _get_text(tt_chung_node, "KHHDon", "InvoiceSeries", "KyHieu")
    # Số hóa đơn (SHDon / InvoiceNumber) - MUST preserve leading zeros!
    sh_hoa_don = _get_text(tt_chung_node, "SHDon", "InvoiceNumber", "SoHoaDon")
    # Ngày lập (NLap / InvoiceDate)
    ngay_lap_raw = _get_text(tt_chung_node, "NLap", "InvoiceDate", "NgayLap")
    ngay_lap = _format_date(ngay_lap_raw)
    # Loại tiền (DVTTe / CurrencyCode)
    loai_tien = _get_text(tt_chung_node, "DVTTe", "CurrencyCode", default="VND")

    # Seller Info (NBan / Seller)
    n_ban = _find_elem(root, "NBan", "Seller")
    n_ban_node = n_ban if n_ban is not None else root
    mst_ban = _get_text(n_ban_node, "MST", "SellerTaxCode", "MaSoThue")
    ten_ban = _get_text(n_ban_node, "Ten", "SellerLegalName", "TenNguoiBan")

    # Buyer Info (NMua / Buyer)
    n_mua = _find_elem(root, "NMua", "Buyer")
    n_mua_node = n_mua if n_mua is not None else root
    mst_mua = _get_text(n_mua_node, "MST", "BuyerTaxCode")
    ten_mua = _get_text(n_mua_node, "Ten", "BuyerLegalName", "TenNguoiMua")

    # Status / Invoice adjustment / replacement
    hd_dieu_chinh = _get_text(tt_chung_node, "HDCTTChinh", "AdjustmentType", "InvoiceType")
    trang_thai = "Gốc" if hd_dieu_chinh in ("0", "", None) else f"Điều chỉnh/Thay thế ({hd_dieu_chinh})"

    # Totals (TToan / Payment / Total)
    t_toan = _find_elem(root, "TToan", "Payment", "TotalSummary")
    t_toan_node = t_toan if t_toan is not None else root
    tien_chua_thue = _parse_number(_get_text(t_toan_node, "TgTCThue", "TotalAmountWithoutVAT", "TienChuaThue"))
    tien_thue = _parse_number(_get_text(t_toan_node, "TgTThue", "TotalVATAmount", "TienThue"))
    chiet_khau = _parse_number(_get_text(t_toan_node, "TTCKTMai", "TotalDiscountAmount", "ChiếtKhấu"))
    phi = _parse_number(_get_text(t_toan_node, "Phi", "TotalFeeAmount"))
    tong_tien = _parse_number(_get_text(t_toan_node, "TgTTTBSo", "TotalAmount", "TongTien"))

    # Validate required fields
    errors = []
    if not mst_ban:
        errors.append("Thiếu MST người bán (MST)")
    if not kh_hoa_don:
        errors.append("Thiếu ký hiệu hóa đơn (KHHDon)")
    if not sh_hoa_don:
        errors.append("Thiếu số hóa đơn (SHDon)")
    if not ngay_lap:
        errors.append("Thiếu ngày lập hóa đơn (NLap)")

    if errors:
        raise XmlParsingError(f"XML thiếu thông tin bắt buộc: {', '.join(errors)}")

    inv_key = InvoiceKey(
        mst_nguoi_ban=mst_ban,
        kh_hoa_don=kh_hoa_don,
        sh_hoa_don=sh_hoa_don,
        ngay_lap=ngay_lap,
    )
    khoa_hd = inv_key.normalized_key()
    xml_filename = inv_key.to_xml_filename()

    # Parse Line Items (DSHHDVu / Products / Items)
    items: List[InvoiceLineItem] = []
    # Find all line item containers: HHDVu or Item or Product
    item_elems = []
    for elem in root.iter():
        clean_tag = elem.tag.split("}")[-1].lower()
        if clean_tag in ("hhdvu", "invoicedetail", "item", "product"):
            item_elems.append(elem)

    for idx, item_elem in enumerate(item_elems, start=1):
        stt_str = _get_text(item_elem, "STT", "LineNumber")
        stt = int(stt_str) if stt_str.isdigit() else idx
        ma_hang = _get_text(item_elem, "MHHDVu", "ItemCode", "ProductCode", "MaHang")
        ten_hang = _get_text(item_elem, "THHDVu", "ItemName", "ProductName", "TenHang")
        dvt = _get_text(item_elem, "DVTinh", "UnitName", "DonViTinh")
        so_luong = _parse_number(_get_text(item_elem, "SLuong", "Quantity"))
        don_gia = _parse_number(_get_text(item_elem, "DGia", "UnitPrice"))
        thanh_tien = _parse_number(_get_text(item_elem, "ThTien", "Amount", "ThanhTien"))
        thue_suat = _get_text(item_elem, "TSuat", "VATRate", "ThueSuat")

        # VAT amount for item (e.g. from TTKhac or direct tag)
        tien_thue_item = _parse_number(_get_text(item_elem, "VATAmount", "TienThue"))
        if tien_thue_item is None:
            # Check inside TTKhac/TTin
            for ttin in item_elem.iter():
                if ttin.tag.split("}")[-1].lower() == "ttin":
                    ttruong = _get_text(ttin, "TTruong")
                    if ttruong.lower() in ("vatamount", "vatamountoc"):
                        tien_thue_item = _parse_number(_get_text(ttin, "DLieu"))
                        break

        items.append(InvoiceLineItem(
            khoa_hoa_don=khoa_hd,
            mst_nguoi_ban=mst_ban,
            kh_hoa_don=kh_hoa_don,
            sh_hoa_don=sh_hoa_don,
            ngay_lap=ngay_lap,
            stt=stt,
            ma_hang=ma_hang,
            ten_hang=ten_hang,
            dvt=dvt,
            so_luong=so_luong,
            don_gia=don_gia,
            thanh_tien=thanh_tien,
            thue_suat=thue_suat,
            tien_thue=tien_thue_item,
            file_xml_nguon=source_filename or xml_filename,
        ))

    header = InvoiceHeader(
        mst_nguoi_ban=mst_ban,
        ten_nguoi_ban=ten_ban,
        mst_nguoi_mua=mst_mua,
        ten_nguoi_mua=ten_mua,
        kh_mau_so=kh_mau_so,
        kh_hoa_don=kh_hoa_don,
        sh_hoa_don=sh_hoa_don,
        ngay_lap=ngay_lap,
        tien_chua_thue=tien_chua_thue,
        tien_thue=tien_thue,
        chiet_khau=chiet_khau,
        phi=phi,
        tong_tien=tong_tien,
        loai_tien=loai_tien,
        trang_thai=trang_thai,
        file_xml=source_filename or xml_filename,
        trang_thai_trich_xuat="THANH_CONG",
        items=items,
    )

    return header


def generate_safe_xml_filename(
    mst_nguoi_ban: str,
    kh_hoa_don: str,
    sh_hoa_don: str,
    ngay_lap: str
) -> str:
    """Generates a standardized filename compliant with Section 5 of SPEC.md.

    Pattern: {MST_NGUOI_BAN}_{KY_HIEU}_{SO_HOA_DON}_{NGAY_LAP}.xml
    Example: 3400401523_C26TNT_00005286_20261009.xml
    """
    key = InvoiceKey(mst_nguoi_ban, kh_hoa_don, sh_hoa_don, ngay_lap)
    return key.to_xml_filename()
