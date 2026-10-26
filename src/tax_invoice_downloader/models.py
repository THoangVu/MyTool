"""Data models for Tax Invoice Downloader."""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class InvoiceKey:
    """Unique key identifier for an invoice."""
    mst_nguoi_ban: str = ""
    kh_hoa_don: str = ""
    sh_hoa_don: str = ""
    ngay_lap: str = ""

    def normalized_key(self) -> str:
        clean_mst = "".join(c for c in self.mst_nguoi_ban.strip() if c.isalnum() or c == "-")
        clean_kh = "".join(c for c in self.kh_hoa_don.strip() if c.isalnum() or c in ("-", "_"))
        clean_sh = "".join(c for c in self.sh_hoa_don.strip() if c.isdigit())
        clean_date = "".join(c for c in self.ngay_lap.strip() if c.isdigit())
        return f"{clean_mst}_{clean_kh}_{clean_sh}_{clean_date}"

    def to_xml_filename(self) -> str:
        """Standard filename: {MST_NGUOI_BAN}_{KY_HIEU}_{SO_HOA_DON}_{NGAY_LAP}.xml"""
        clean_mst = "".join(c for c in self.mst_nguoi_ban.strip() if c.isalnum() or c == "-")
        clean_kh = "".join(c for c in self.kh_hoa_don.strip() if c.isalnum() or c in ("-", "_"))
        clean_sh = "".join(c for c in self.sh_hoa_don.strip() if c.isalnum())
        # Format date as YYYYMMDD
        clean_date = "".join(c for c in self.ngay_lap.strip() if c.isdigit())
        if len(clean_date) > 8:
            clean_date = clean_date[:8]
        return f"{clean_mst}_{clean_kh}_{clean_sh}_{clean_date}.xml"


@dataclass
class InvoiceLineItem:
    """One line item in an invoice."""
    khoa_hoa_don: str = ""
    mst_nguoi_ban: str = ""
    kh_hoa_don: str = ""
    sh_hoa_don: str = ""
    ngay_lap: str = ""
    stt: Optional[int] = None
    ma_hang: str = ""
    ten_hang: str = ""
    dvt: str = ""
    so_luong: Optional[float] = None
    don_gia: Optional[float] = None
    thanh_tien: Optional[float] = None
    thue_suat: str = ""
    tien_thue: Optional[float] = None
    file_xml_nguon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InvoiceHeader:
    """Invoice header information."""
    mst_nguoi_ban: str = ""
    ten_nguoi_ban: str = ""
    mst_nguoi_mua: str = ""
    ten_nguoi_mua: str = ""
    kh_mau_so: str = ""
    kh_hoa_don: str = ""
    sh_hoa_don: str = ""
    ngay_lap: str = ""
    tien_chua_thue: Optional[float] = 0.0
    tien_thue: Optional[float] = 0.0
    chiet_khau: Optional[float] = 0.0
    phi: Optional[float] = 0.0
    tong_tien: Optional[float] = 0.0
    loai_tien: str = "VND"
    trang_thai: str = ""
    file_xml: str = ""
    trang_thai_trich_xuat: str = "CHUA_XU_LY"
    ghi_chu: str = ""
    items: List[InvoiceLineItem] = field(default_factory=list)

    @property
    def invoice_key(self) -> InvoiceKey:
        return InvoiceKey(
            mst_nguoi_ban=self.mst_nguoi_ban,
            kh_hoa_don=self.kh_hoa_don,
            sh_hoa_don=self.sh_hoa_don,
            ngay_lap=self.ngay_lap,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("items", None)
        return d


@dataclass
class DownloadHistoryRecord:
    """History entry for downloading/processing an invoice."""
    thoi_diem: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    khoa_hoa_don: str = ""
    trang_thai: str = "PENDING"
    so_lan_thu: int = 0
    ten_zip_tam: str = ""
    ten_xml_dau_ra: str = ""
    thong_bao_loi: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SummaryStats:
    """Execution summary statistics."""
    so_dong_tim_thay: int = 0
    so_da_tai: int = 0
    so_xml_thanh_cong: int = 0
    so_loi: int = 0
    so_bo_qua: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
