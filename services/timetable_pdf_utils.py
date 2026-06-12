"""
Timetable PDF utility functions.

- normalize_class_code: strips parentheses content, trims, uppercases
- extract_pages_for_class_code: scans active PDF with pdfplumber (text search)
  and extracts matching pages with pypdf, returning PDF bytes in memory.
"""

import io
import logging
import re

logger = logging.getLogger(__name__)


def normalize_class_code(raw: str) -> str:
    """Normalize a class code for consistent lookup.

    Rules:
    - Strip anything in parentheses (including the parens themselves)
    - Trim surrounding whitespace
    - Uppercase
    - Collapse multiple hyphens

    Examples:
        "FA22-BCS-8A (21)" -> "FA22-BCS-8A"
        "FA22-BCS-8A(21)"  -> "FA22-BCS-8A"
        "fa22-bcs-8a"      -> "FA22-BCS-8A"
    """
    if not raw:
        return ""
    value = re.sub(r"\s*\(.*?\)\s*", "", str(raw))
    value = value.strip().upper()
    value = re.sub(r"-+", "-", value)
    return value


def extract_pages_for_class_code(pdf_path: str, class_code: str) -> bytes:
    """Scan all pages of the PDF at *pdf_path* for *class_code* (case-insensitive
    substring match) using pdfplumber, then extract only the matching pages into
    a new in-memory PDF using pypdf.

    Returns:
        bytes: the filtered PDF binary (never written to disk).

    Raises:
        FileNotFoundError: if *pdf_path* does not exist.
        RuntimeError: if no matching pages are found.
        ImportError: if pdfplumber or pypdf is not installed.
    """
    import os
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"Timetable PDF not found: {pdf_path}")

    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is required. Install with: pip install pdfplumber") from exc

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        try:
            from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
        except ImportError as exc:
            raise ImportError("pypdf is required. Install with: pip install pypdf") from exc

    normalized = normalize_class_code(class_code)
    search_term = normalized.upper()

    matching_page_indices = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text() or ""
                    if search_term in text.upper():
                        matching_page_indices.append(page_idx)
                except Exception as exc:
                    logger.warning("pdfplumber failed on page %d: %s", page_idx, exc)
    except Exception as exc:
        logger.error("pdfplumber could not open PDF: %s", exc)
        raise RuntimeError(f"Failed to read PDF: {exc}") from exc

    if not matching_page_indices:
        raise RuntimeError(f"NO_MATCH:{normalized}")

    # Extract matching pages into a new in-memory PDF
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        for idx in matching_page_indices:
            writer.add_page(reader.pages[idx])

        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        return output_buffer.getvalue()
    except Exception as exc:
        logger.error("pypdf page extraction failed: %s", exc)
        raise RuntimeError(f"Failed to extract PDF pages: {exc}") from exc
