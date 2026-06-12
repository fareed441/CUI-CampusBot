"""PDF timetable processing service.

Responsibilities:
- Split an uploaded centralized timetable PDF page-by-page.
- Extract class code per page using regex.
- Store each page as its own PDF in storage/uploads/timetables/.
- Upsert metadata into MongoDB.

This module does not define web routes; it is called by Flask/FastAPI endpoints.
"""

from __future__ import annotations

import os
import tempfile
import logging
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from pymongo.database import Database

from api.pdf_timetable_store import (
    extract_class_code_from_text,
    build_storage_paths,
    get_timetable_record,
    normalize_class_code,
    project_root_from_api_dir,
    upsert_timetable_record,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageProcessResult:
    class_code: str
    original_page_number: int
    replaced: bool
    file_path: str  # relative path


@dataclass(frozen=True)
class PDFProcessSummary:
    total_pages: int
    processed_pages: int
    skipped_pages: int
    results: List[PageProcessResult]
    skipped_page_numbers: List[int]


class PDFProcessingError(RuntimeError):
    pass


def _ensure_storage_dir(abs_file_path: str) -> None:
    os.makedirs(os.path.dirname(abs_file_path), exist_ok=True)


def _atomic_write_bytes(target_path: str, data: bytes) -> None:
    """Write bytes to target path atomically (best-effort on Windows)."""
    _ensure_storage_dir(target_path)

    with tempfile.NamedTemporaryFile(delete=False, dir=os.path.dirname(target_path), suffix=".tmp") as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name

    try:
        os.replace(tmp_path, target_path)
    except Exception:
        # Clean temp file on failure.
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise


def process_master_timetable_pdf(
    *,
    db: Database,
    pdf_bytes: bytes,
    original_filename: str,
    project_root: Optional[str] = None,
) -> PDFProcessSummary:
    """Process the uploaded master PDF.

    Args:
        db: pymongo Database
        pdf_bytes: raw PDF bytes
        original_filename: used for diagnostics/logging
        project_root: optional explicit project root. If omitted, resolved from this module location.

    Returns:
        PDFProcessSummary

    Raises:
        PDFProcessingError: invalid/unreadable PDF or no class codes detected.
    """
    if not pdf_bytes:
        raise PDFProcessingError("Uploaded PDF is empty")

    project_root = project_root or project_root_from_api_dir(__file__)

    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.errors import PdfReadError
    except Exception as e:
        raise PDFProcessingError(f"PDF library not available: {e}")

    # Extract text per page using pdfplumber (more reliable for structured PDFs).
    try:
        import pdfplumber
    except Exception as e:
        raise PDFProcessingError(f"pdfplumber is not installed or failed to import: {e}")

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
    except Exception as e:
        raise PDFProcessingError(f"Invalid or unreadable PDF: {e}")

    if total_pages <= 0:
        raise PDFProcessingError("PDF has no pages")

    results: List[PageProcessResult] = []
    skipped_pages: List[int] = []

    upload_time = datetime.utcnow()

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) != total_pages:
                logger.warning(
                    "[TIMETABLE PDF] Page count mismatch between parsers: pypdf=%s pdfplumber=%s (file=%s)",
                    total_pages,
                    len(pdf.pages),
                    original_filename,
                )

            for idx in range(total_pages):
                page_number = idx + 1

                page_text = ""
                try:
                    page_text = (pdf.pages[idx].extract_text() or "") if idx < len(pdf.pages) else ""
                except Exception as e:
                    logger.warning(
                        "[TIMETABLE PDF] Text extraction failed on page %s (%s): %s",
                        page_number,
                        original_filename,
                        e,
                    )
                    page_text = ""

                class_code = extract_class_code_from_text(page_text)
                if not class_code:
                    skipped_pages.append(page_number)
                    continue

                class_code = normalize_class_code(class_code)

                # Determine whether this class code already exists.
                existing = get_timetable_record(db, class_code)
                replaced = bool(existing)

                abs_path, rel_path = build_storage_paths(project_root, class_code)

                # Write single-page PDF.
                writer = PdfWriter()
                writer.add_page(reader.pages[idx])
                output_stream = BytesIO()
                writer.write(output_stream)
                _atomic_write_bytes(abs_path, output_stream.getvalue())

                # If an existing record points to a different file path, attempt cleanup.
                if existing and existing.get("file_path") and existing.get("file_path") != rel_path:
                    old_abs = os.path.join(project_root, *str(existing["file_path"]).split("/"))
                    if os.path.isfile(old_abs) and old_abs != abs_path:
                        try:
                            os.remove(old_abs)
                        except Exception:
                            # Non-fatal.
                            logger.info(
                                "[TIMETABLE PDF] Could not delete old file %s for %s",
                                old_abs,
                                class_code,
                            )

                upsert_timetable_record(
                    db,
                    class_code=class_code,
                    relative_file_path=rel_path,
                    original_page_number=page_number,
                    uploaded_at=upload_time,
                )

                results.append(
                    PageProcessResult(
                        class_code=class_code,
                        original_page_number=page_number,
                        replaced=replaced,
                        file_path=rel_path,
                    )
                )

    except PdfReadError as e:
        raise PDFProcessingError(f"Invalid or unreadable PDF: {e}")
    except PDFProcessingError:
        raise
    except Exception as e:
        raise PDFProcessingError(f"Failed to process PDF: {e}")

    if not results:
        raise PDFProcessingError(
            "No class codes were detected in the uploaded PDF. "
            "Ensure the PDF is text-based (not scanned) and contains class codes like 'BCS-SP26-1'."
        )

    return PDFProcessSummary(
        total_pages=total_pages,
        processed_pages=len(results),
        skipped_pages=len(skipped_pages),
        results=results,
        skipped_page_numbers=skipped_pages,
    )
