"""PDF-based class timetable storage (MongoDB metadata + filesystem PDFs).

This module is intentionally framework-agnostic so it can be used by:
- Flask app (app.py)
- FastAPI app (app/main.py) via api/timetable_api.py

Storage model:
- Split class-wise timetable pages are stored on disk under:
  storage/uploads/timetables/<CLASS_CODE>.pdf
- MongoDB stores metadata only.

Required behavior:
- Case-insensitive lookup
- Trim spaces
- Replace existing record/files on re-upload
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pymongo.collection import Collection
from pymongo.database import Database


# Recommended class code regex:
# \b[A-Z]{2,5}-[A-Z]{2}\d{2}-\d+[A-Z]?\b
CLASS_CODE_REGEX = re.compile(r"\b[A-Z]{2,5}-[A-Z]{2}\d{2}-\d+[A-Z]?\b", re.IGNORECASE)

_TRAILING_COUNT_REGEX = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


TIMETABLE_COLLECTION_NAME = "class_timetables"
TIMETABLE_STORAGE_REL_DIR = "storage/uploads/timetables"


@dataclass(frozen=True)
class ClassTimetableRecord:
    class_code: str
    file_path: str  # POSIX-like relative path, e.g. storage/uploads/timetables/BCS-SP26-1.pdf
    uploaded_at: datetime
    original_page_number: int


def project_root_from_api_dir(api_file_path: str) -> str:
    """Return project root path from a file inside api/ folder."""
    return os.path.dirname(os.path.dirname(os.path.abspath(api_file_path)))


def normalize_class_code(raw: str) -> str:
    """Normalize class code for consistent DB keys.

    Rules:
    - Trim
    - Uppercase
    - Remove any trailing student-count brackets, e.g. "(21)"
    - Remove all whitespace (users may type with spaces)
    - Collapse multiple hyphens
    """
    if not raw:
        return ""

    value = str(raw).strip()
    value = _TRAILING_COUNT_REGEX.sub("", value)
    value = value.upper()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"-+", "-", value)
    return value


def extract_class_code_from_text(text: str) -> Optional[str]:
    """Extract first matching class code from page text."""
    if not text:
        return None

    match = CLASS_CODE_REGEX.search(text)
    if not match:
        return None

    return normalize_class_code(match.group(0))


def sanitize_class_code_for_filename(class_code: str) -> str:
    """Sanitize class code to a safe filename component."""
    value = normalize_class_code(class_code)
    # Keep only alnum, dash, underscore.
    value = re.sub(r"[^A-Z0-9_-]", "_", value)
    return value


def _ensure_indexes(collection: Collection) -> None:
    """Create indexes needed by the PDF timetable system."""
    # Unique class_code for replace-on-upload behavior.
    collection.create_index("class_code", unique=True)
    collection.create_index("uploaded_at")


def get_timetable_collection(db: Database) -> Collection:
    collection = db[TIMETABLE_COLLECTION_NAME]
    _ensure_indexes(collection)
    return collection


def build_storage_paths(project_root: str, class_code: str) -> tuple[str, str]:
    """Return (absolute_path, relative_posix_path) for a class timetable PDF."""
    safe_code = sanitize_class_code_for_filename(class_code)
    rel_posix = f"{TIMETABLE_STORAGE_REL_DIR}/{safe_code}.pdf"
    abs_path = os.path.join(project_root, *rel_posix.split("/"))
    return abs_path, rel_posix


def upsert_timetable_record(
    db: Database,
    *,
    class_code: str,
    relative_file_path: str,
    original_page_number: int,
    uploaded_at: Optional[datetime] = None,
) -> dict:
    """Upsert timetable record. Returns MongoDB update result metadata."""
    uploaded_at = uploaded_at or datetime.utcnow()
    normalized_code = normalize_class_code(class_code)

    collection = get_timetable_collection(db)
    return collection.update_one(
        {"class_code": normalized_code},
        {
            "$set": {
                "class_code": normalized_code,
                "file_path": relative_file_path,
                "original_page_number": int(original_page_number),
                "uploaded_at": uploaded_at,
            }
        },
        upsert=True,
    ).raw_result


def get_timetable_record(db: Database, class_code: str) -> Optional[dict]:
    normalized_code = normalize_class_code(class_code)
    if not normalized_code:
        return None

    collection = get_timetable_collection(db)
    return collection.find_one({"class_code": normalized_code}, {"_id": 0})
