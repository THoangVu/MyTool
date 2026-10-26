"""Extracts invoice.xml from downloaded ZIP archives safely in memory."""

import io
import os
import zipfile
from pathlib import Path
from typing import Union, Optional


class ZipExtractionError(Exception):
    """Custom exception raised when ZIP extraction fails or violates safety rules."""
    pass


def extract_invoice_xml_bytes(
    zip_source: Union[str, Path, bytes, io.BytesIO],
    max_size_bytes: int = 20 * 1024 * 1024
) -> bytes:
    """Safely extracts the raw bytes of invoice.xml from a ZIP archive in memory.

    Rules:
    - Only extracts members ending with 'invoice.xml' (case-insensitive).
    - Ignores all other files (details.js, invoice.html, images, etc.).
    - Rejects archives with 0 or >1 invoice.xml members.
    - Prevents zip-slip and enforces maximum uncompressed size limit.
    """
    if isinstance(zip_source, (str, Path)):
        zip_path = Path(zip_source)
        if not zip_path.is_file():
            raise ZipExtractionError(f"File ZIP không tồn tại: {zip_path}")
        if zip_path.stat().st_size == 0:
            raise ZipExtractionError("File ZIP rỗng (0 bytes)")
        source = zip_path
    elif isinstance(zip_source, bytes):
        if len(zip_source) == 0:
            raise ZipExtractionError("Dữ liệu ZIP rỗng (0 bytes)")
        source = io.BytesIO(zip_source)
    elif isinstance(zip_source, io.BytesIO):
        source = zip_source
    else:
        raise ZipExtractionError("Nguồn ZIP không hợp lệ")

    try:
        with zipfile.ZipFile(source, mode="r") as zf:
            candidates = []
            for info in zf.infolist():
                # Prevent directory entries
                if info.is_dir():
                    continue
                # Normalize filename check
                normalized_name = os.path.basename(info.filename).strip().lower()
                if normalized_name == "invoice.xml" or info.filename.lower().endswith("/invoice.xml") or info.filename.lower().endswith("\\invoice.xml"):
                    # Check path traversal
                    if ".." in info.filename or info.filename.startswith("/") or info.filename.startswith("\\"):
                        raise ZipExtractionError(f"Phát hiện đường dẫn không an toàn trong ZIP: {info.filename}")
                    candidates.append(info)

            if not candidates:
                raise ZipExtractionError("Không tìm thấy file invoice.xml trong file ZIP")

            if len(candidates) > 1:
                names = [c.filename for c in candidates]
                raise ZipExtractionError(f"Phát hiện nhiều file invoice.xml trong ZIP: {names}")

            target_info = candidates[0]

            # Check uncompressed size limit
            if target_info.file_size > max_size_bytes:
                raise ZipExtractionError(
                    f"Kích thước file invoice.xml ({target_info.file_size} bytes) vượt quá giới hạn cho phép ({max_size_bytes} bytes)"
                )

            xml_bytes = zf.read(target_info)
            if not xml_bytes or len(xml_bytes.strip()) == 0:
                raise ZipExtractionError("File invoice.xml bên trong ZIP bị rỗng")

            return xml_bytes

    except zipfile.BadZipFile as e:
        raise ZipExtractionError(f"File không phải định dạng ZIP hợp lệ hoặc bị hỏng: {e}") from e
    except ZipExtractionError:
        raise
    except Exception as e:
        raise ZipExtractionError(f"Lỗi khi đọc file ZIP: {e}") from e


def extract_and_save_invoice_xml(
    zip_source: Union[str, Path, bytes, io.BytesIO],
    destination_path: Union[str, Path],
    max_size_bytes: int = 20 * 1024 * 1024
) -> Path:
    """Extracts invoice.xml bytes and saves directly to destination_path."""
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = extract_invoice_xml_bytes(zip_source, max_size_bytes=max_size_bytes)
    dest.write_bytes(xml_bytes)
    return dest
