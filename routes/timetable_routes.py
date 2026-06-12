"""
New Timetable Blueprint — PDF upload/management + class-code lookup.

Endpoints:
  POST   /api/admin/timetable/upload          Upload a new timetable PDF
  GET    /api/admin/timetable/list            List all uploaded timetables
  DELETE /api/admin/timetable/<id>            Delete a timetable record + file
  PATCH  /api/admin/timetable/<id>/activate   Set one active, deactivate others
  GET    /api/timetable/active                Public: get active timetable info
  GET    /api/timetable/download/full         Public: stream active full PDF (attachment)
  POST   /api/timetable/lookup               Public: extract pages for class code → JSON
  GET    /api/timetable/preview/<filename>    Public: serve temp PDF inline (for iframe)
  GET    /api/timetable/download/class/<filename>  Public: download temp PDF as attachment
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request, send_file

from database.mongodb import db
from services.timetable_pdf_utils import extract_pages_for_class_code, normalize_class_code

logger = logging.getLogger(__name__)

timetable_bp = Blueprint("timetable_v2", __name__)

# Persistent upload directory (relative to project root)
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "uploads", "timetables", "full"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Temp directory for class-filtered PDFs
TEMP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "uploads", "timetables", "temp"
)
os.makedirs(TEMP_DIR, exist_ok=True)

COLLECTION = "uploaded_timetables"


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _as_oid(value: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _record_to_dict(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "filename": doc.get("filename", ""),
        "original_name": doc.get("original_name", ""),
        "file_path": doc.get("file_path", ""),
        "is_active": doc.get("is_active", False),
        "uploaded_at": doc["uploaded_at"].isoformat() if doc.get("uploaded_at") else None,
    }


def _get_active_record() -> dict | None:
    return db[COLLECTION].find_one({"is_active": True})


def cleanup_temp_pdfs(temp_dir: str, max_age_seconds: int = 3600):
    """Delete temp PDF files older than max_age_seconds."""
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)
        return
    now = time.time()
    for f in os.listdir(temp_dir):
        fpath = os.path.join(temp_dir, f)
        if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
            try:
                os.remove(fpath)
            except OSError as e:
                logger.warning("Could not delete temp file %s: %s", fpath, e)


# ─────────────────────────────────────────────────────────────
# Admin — Upload
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/admin/timetable/upload", methods=["POST"])
def upload_timetable():
    """Accept PDF upload, save to disk, update DB."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        uploaded_file = request.files["file"]
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({"error": "No file selected"}), 400

        if not uploaded_file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are accepted"}), 400

        file_bytes = uploaded_file.read()
        if not file_bytes:
            return jsonify({"error": "Uploaded file is empty"}), 400

        # Build safe timestamped filename
        original_name = uploaded_file.filename
        safe_filename = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}_{original_name}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Deactivate all existing records
        db[COLLECTION].update_many({}, {"$set": {"is_active": False}})

        # Insert new active record
        now = datetime.now(timezone.utc)
        doc = {
            "filename": safe_filename,
            "original_name": original_name,
            "file_path": file_path,
            "is_active": True,
            "uploaded_at": now,
        }
        result = db[COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id

        return jsonify({"success": True, "record": _record_to_dict(doc)}), 201

    except Exception as exc:
        logger.error("upload_timetable error: %s", exc)
        return jsonify({"error": f"Upload failed: {exc}"}), 500


# ─────────────────────────────────────────────────────────────
# Admin — List
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/admin/timetable/list", methods=["GET"])
def list_timetables():
    """Return all uploaded timetable records."""
    try:
        docs = list(db[COLLECTION].find().sort("uploaded_at", -1))
        return jsonify([_record_to_dict(d) for d in docs])
    except Exception as exc:
        logger.error("list_timetables error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Admin — Delete
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/admin/timetable/<timetable_id>", methods=["DELETE"])
def delete_timetable(timetable_id):
    """Delete a timetable record and its file from disk."""
    try:
        oid = _as_oid(timetable_id)
        if not oid:
            return jsonify({"error": "Invalid timetable id"}), 400

        doc = db[COLLECTION].find_one({"_id": oid})
        if not doc:
            return jsonify({"error": "Timetable not found"}), 404

        # Remove file from disk
        fp = doc.get("file_path", "")
        if fp and os.path.isfile(fp):
            try:
                os.remove(fp)
            except OSError as e:
                logger.warning("Could not delete file %s: %s", fp, e)

        db[COLLECTION].delete_one({"_id": oid})
        return jsonify({"success": True})

    except Exception as exc:
        logger.error("delete_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Admin — Set Active
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/admin/timetable/<timetable_id>/activate", methods=["PATCH"])
def activate_timetable(timetable_id):
    """Mark one timetable as active, deactivate all others."""
    try:
        oid = _as_oid(timetable_id)
        if not oid:
            return jsonify({"error": "Invalid timetable id"}), 400

        doc = db[COLLECTION].find_one({"_id": oid})
        if not doc:
            return jsonify({"error": "Timetable not found"}), 404

        db[COLLECTION].update_many({}, {"$set": {"is_active": False}})
        db[COLLECTION].update_one({"_id": oid}, {"$set": {"is_active": True}})

        updated = db[COLLECTION].find_one({"_id": oid})
        return jsonify({"success": True, "record": _record_to_dict(updated)})

    except Exception as exc:
        logger.error("activate_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Active timetable info
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/timetable/active", methods=["GET"])
def get_active_timetable():
    """Return active timetable metadata."""
    try:
        doc = _get_active_record()
        if not doc:
            return jsonify({"error": "No active timetable"}), 404
        return jsonify(_record_to_dict(doc))
    except Exception as exc:
        logger.error("get_active_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Download full active PDF (attachment)
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/timetable/download/full", methods=["GET"])
def download_full_timetable():
    """Stream the full active timetable PDF as a download attachment."""
    try:
        doc = _get_active_record()
        if not doc:
            return jsonify({"error": "No timetable has been uploaded yet. Please check back later."}), 404

        fp = doc.get("file_path", "")
        if not fp or not os.path.isfile(fp):
            return jsonify({"error": "Timetable file is missing on server"}), 404

        original_name = doc.get("original_name", "timetable.pdf")

        return send_file(
            fp,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=original_name,
        )

    except Exception as exc:
        logger.error("download_full_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Class code lookup (page extraction) → returns JSON
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/timetable/lookup", methods=["POST"])
def lookup_timetable():
    """Extract pages matching a class code from the active timetable PDF.

    Body (JSON): { "class_code": "FA22-BCS-8A" }
    Returns: JSON with view_url and download_url for the temp filtered PDF.
    """
    try:
        # Clean up old temp files first
        cleanup_temp_pdfs(TEMP_DIR)

        data = request.get_json(silent=True) or {}
        raw_code = data.get("class_code", "").strip()

        if not raw_code:
            return jsonify({"error": "class_code is required"}), 400

        normalized = normalize_class_code(raw_code)
        if not normalized:
            return jsonify({"error": "Invalid class code"}), 400

        doc = _get_active_record()
        if not doc:
            return jsonify({"error": "No timetable has been uploaded yet. Please check back later."}), 404

        fp = doc.get("file_path", "")
        if not fp or not os.path.isfile(fp):
            return jsonify({"error": "Timetable file is missing on server"}), 404

        try:
            pdf_bytes = extract_pages_for_class_code(fp, normalized)
        except RuntimeError as exc:
            err_str = str(exc)
            if err_str.startswith("NO_MATCH:"):
                code = err_str[len("NO_MATCH:"):]
                return jsonify({"error": f"No timetable found for class code: {code}"}), 404
            return jsonify({"error": err_str}), 500

        # Count pages in extracted PDF
        pages_found = 0
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_found = len(reader.pages)
        except Exception:
            pages_found = 1  # fallback

        # Save to temp file
        safe_code = normalized.replace("/", "-").replace("\\", "-").replace('"', "")
        short_id = uuid.uuid4().hex[:8]
        temp_filename = f"{safe_code}_{short_id}.pdf"
        temp_path = os.path.join(TEMP_DIR, temp_filename)

        with open(temp_path, "wb") as f:
            f.write(pdf_bytes)

        return jsonify({
            "success": True,
            "view_url": f"/api/timetable/preview/{temp_filename}",
            "download_url": f"/api/timetable/download/class/{temp_filename}",
            "class_code": normalized,
            "pages_found": pages_found,
        })

    except Exception as exc:
        logger.error("lookup_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Serve temp PDF inline (for iframe embedding)
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/timetable/preview/<filename>", methods=["GET"])
def preview_timetable(filename):
    """Serve a temp filtered PDF inline so it can be embedded in an iframe."""
    try:
        # Basic filename safety — no path traversal
        safe_filename = os.path.basename(filename)
        temp_path = os.path.join(TEMP_DIR, safe_filename)

        if not os.path.isfile(temp_path):
            return jsonify({"error": "Preview not found or expired. Please search again."}), 404

        response = send_file(
            temp_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=safe_filename,
        )
        # Allow iframe embedding from same origin
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'
        return response

    except Exception as exc:
        logger.error("preview_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Download temp PDF as attachment
# ─────────────────────────────────────────────────────────────

@timetable_bp.route("/api/timetable/download/class/<filename>", methods=["GET"])
def download_class_timetable(filename):
    """Download a temp filtered PDF as an attachment."""
    try:
        safe_filename = os.path.basename(filename)
        temp_path = os.path.join(TEMP_DIR, safe_filename)

        if not os.path.isfile(temp_path):
            return jsonify({"error": "File not found or expired. Please search again."}), 404

        # Derive a nice download name from the filename (strip the uuid suffix)
        # e.g. "FA22-BCS-8A_a3f9b2c1.pdf" → "FA22-BCS-8A-timetable.pdf"
        base = safe_filename.rsplit("_", 1)[0] if "_" in safe_filename else safe_filename.replace(".pdf", "")
        download_name = f"{base}-timetable.pdf"

        return send_file(
            temp_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )

    except Exception as exc:
        logger.error("download_class_timetable error: %s", exc)
        return jsonify({"error": str(exc)}), 500
