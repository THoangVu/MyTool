"""Tax Invoice Downloader package."""

from .models import (
    InvoiceKey,
    InvoiceHeader,
    InvoiceLineItem,
    DownloadHistoryRecord,
    SummaryStats,
)
from .logging_config import setup_logger, ManifestDB
from .zip_xml_extractor import extract_invoice_xml_bytes, extract_and_save_invoice_xml, ZipExtractionError
from .xml_parser import parse_invoice_xml, generate_safe_xml_filename, XmlParsingError
from .excel_exporter import export_invoices_to_excel, export_from_allinvoice_folder
from .download_manager import DownloadManager, DownloadManagerError
from .browser_session import BrowserSessionManager
from .tax_portal import TaxPortalAutomation, SessionExpiredError

__all__ = [
    "InvoiceKey",
    "InvoiceHeader",
    "InvoiceLineItem",
    "DownloadHistoryRecord",
    "SummaryStats",
    "setup_logger",
    "ManifestDB",
    "extract_invoice_xml_bytes",
    "extract_and_save_invoice_xml",
    "ZipExtractionError",
    "parse_invoice_xml",
    "generate_safe_xml_filename",
    "XmlParsingError",
    "export_invoices_to_excel",
    "export_from_allinvoice_folder",
    "DownloadManager",
    "DownloadManagerError",
    "BrowserSessionManager",
    "TaxPortalAutomation",
    "SessionExpiredError",
]
