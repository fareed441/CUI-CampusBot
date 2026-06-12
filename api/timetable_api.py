"""PDF Timetable API (FastAPI).

This completely replaces the legacy generator/CRUD/export timetable system.

Endpoints:
- POST /api/timetable/admin/upload-pdf  (admin-only)
- GET  /api/timetable/class/{class_code}
- GET  /api/timetable/class/{class_code}/pdf      (inline)
- GET  /api/timetable/class/{class_code}/download (attachment)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.pdf_timetable_service import PDFProcessingError, process_master_timetable_pdf
from api.pdf_timetable_store import (
    get_timetable_record,
    normalize_class_code,
    project_root_from_api_dir,
)
from app.database import get_database
from app.dependencies import get_admin_user

router = APIRouter(prefix="/api/timetable", tags=["Timetable (PDF)"])


def _project_root() -> str:
    return project_root_from_api_dir(__file__)


def _resolve_abs_path(project_root: str, relative_posix_path: str) -> str:
    abs_path = os.path.normpath(os.path.join(project_root, *relative_posix_path.split("/")))

    allowed_root = os.path.normpath(os.path.join(project_root, "storage", "uploads", "timetables"))
    if not abs_path.startswith(allowed_root):
        raise HTTPException(status_code=500, detail="Invalid timetable file path in database")

    return abs_path


def _record_to_response(record: Dict[str, Any]) -> Dict[str, Any]:
    uploaded_at = record.get("uploaded_at")
    if isinstance(uploaded_at, datetime):
        uploaded_at = uploaded_at.isoformat()

    return {
        "class_code": record.get("class_code"),
        "file_path": record.get("file_path"),
        "uploaded_at": uploaded_at,
        "original_page_number": record.get("original_page_number"),
    }


@router.post("/admin/upload-pdf")
async def admin_upload_timetable_pdf(
    file: UploadFile = File(...),
    _admin_user: dict = Depends(get_admin_user),
    database=Depends(get_database),
):
    """Upload centralized timetable PDF and split into per-class PDFs."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    pdf_bytes = await file.read()

    try:
        summary = process_master_timetable_pdf(
            db=database.db,
            pdf_bytes=pdf_bytes,
            original_filename=file.filename,
        )
    except PDFProcessingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process timetable PDF: {e}")

    class_codes = [r.class_code for r in summary.results]
    replaced_codes = [r.class_code for r in summary.results if r.replaced]

    return {
        "status": "success",
        "message": "Timetable PDF processed successfully",
        "total_pages": summary.total_pages,
        "processed_pages": summary.processed_pages,
        "skipped_pages": summary.skipped_pages,
        "skipped_page_numbers": summary.skipped_page_numbers,
        "class_codes": class_codes,
        "replaced_class_codes": replaced_codes,
    }


@router.get("/class/{class_code}")
async def get_class_timetable(class_code: str, database=Depends(get_database)):
    """Get timetable metadata for a class code."""
    normalized = normalize_class_code(class_code)
    if not normalized:
        raise HTTPException(status_code=400, detail="Class code is required")

    record = get_timetable_record(database.db, normalized)
    if not record:
        raise HTTPException(status_code=404, detail="No timetable found for this class code")

    return _record_to_response(record)


@router.get("/class/{class_code}/pdf")
async def view_class_timetable_pdf(class_code: str, database=Depends(get_database)):
    """Inline PDF view for a class timetable."""
    normalized = normalize_class_code(class_code)
    if not normalized:
        raise HTTPException(status_code=400, detail="Class code is required")

    record = get_timetable_record(database.db, normalized)
    if not record:
        raise HTTPException(status_code=404, detail="No timetable found for this class code")

    project_root = _project_root()
    abs_path = _resolve_abs_path(project_root, record["file_path"])

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Timetable PDF file is missing on server")

    return FileResponse(
        abs_path,
        media_type="application/pdf",
        filename=f"{normalized}.pdf",
        headers={"Content-Disposition": f"inline; filename={normalized}.pdf"},
    )


@router.get("/class/{class_code}/download")
async def download_class_timetable_pdf(class_code: str, database=Depends(get_database)):
    """Download PDF for a class timetable."""
    normalized = normalize_class_code(class_code)
    if not normalized:
        raise HTTPException(status_code=400, detail="Class code is required")

    record = get_timetable_record(database.db, normalized)
    if not record:
        raise HTTPException(status_code=404, detail="No timetable found for this class code")

    project_root = _project_root()
    abs_path = _resolve_abs_path(project_root, record["file_path"])

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Timetable PDF file is missing on server")

    return FileResponse(
        abs_path,
        media_type="application/pdf",
        filename=f"{normalized}.pdf",
        headers={"Content-Disposition": f"attachment; filename={normalized}.pdf"},
    )
