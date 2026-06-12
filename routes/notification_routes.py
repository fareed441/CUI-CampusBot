"""
Notifications Blueprint.

Endpoints:
  POST   /api/admin/notifications        Create a notification with optional file attachment (admin)
  GET    /api/admin/notifications        List all notifications (admin)
  DELETE /api/admin/notifications/<id>   Delete a notification (admin)
  GET    /api/notifications              Public: list newest-first
  GET    /uploads/notifications/<filename>  Serve uploaded attachment file
"""

import logging
import os
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request, send_file

from database.mongodb import db

logger = logging.getLogger(__name__)

notification_bp = Blueprint("notifications_v2", __name__)

COLLECTION = "notifications"

VALID_TYPES = {"general", "midterm", "finalterm", "datesheet", "urgent"}

# Upload directory for notification attachments
NOTIF_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage", "uploads", "notifications"
)
os.makedirs(NOTIF_UPLOAD_DIR, exist_ok=True)

# Allowed extensions and their attachment_type mapping
ALLOWED_EXTENSIONS = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".webp": "image",
    ".pdf": "pdf",
    ".docx": "docx",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _as_oid(value: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _doc_to_dict(doc: dict) -> dict:
    created_at = doc.get("created_at")
    attachment_filename = doc.get("attachment_filename")
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "body": doc.get("body", ""),
        "type": doc.get("type", "general"),
        "created_at": created_at.isoformat() if created_at else None,
        "attachment_filename": attachment_filename,
        "attachment_original_name": doc.get("attachment_original_name"),
        "attachment_type": doc.get("attachment_type"),
        "attachment_url": f"/uploads/notifications/{attachment_filename}" if attachment_filename else None,
    }


# ─────────────────────────────────────────────────────────────
# Admin — Create (multipart/form-data with optional file)
# ─────────────────────────────────────────────────────────────

@notification_bp.route("/api/admin/notifications", methods=["POST"])
def create_notification():
    """Create a new notification, optionally with a file attachment."""
    try:
        # Accept form data (multipart) to support file uploads
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        ntype = (request.form.get("type") or "general").strip().lower()

        if not title:
            return jsonify({"error": "title is required"}), 400
        if not body or len(body) < 10:
            return jsonify({"error": "body must be at least 10 characters"}), 400
        if ntype not in VALID_TYPES:
            ntype = "general"

        # Handle optional file attachment
        attachment_filename = None
        attachment_original_name = None
        attachment_type = None

        uploaded_file = request.files.get("attachment")
        if uploaded_file and uploaded_file.filename:
            original_name = uploaded_file.filename
            ext = os.path.splitext(original_name)[1].lower()

            if ext not in ALLOWED_EXTENSIONS:
                return jsonify({
                    "error": "Unsupported file type. Allowed: JPG, PNG, GIF, WEBP, PDF, DOCX"
                }), 400

            # Read and check size
            file_bytes = uploaded_file.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                return jsonify({"error": "File too large. Maximum size is 10MB."}), 400

            # Save with unique name
            unique_name = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(NOTIF_UPLOAD_DIR, unique_name)
            with open(save_path, "wb") as f:
                f.write(file_bytes)

            attachment_filename = unique_name
            attachment_original_name = original_name
            attachment_type = ALLOWED_EXTENSIONS[ext]

        doc = {
            "title": title,
            "body": body,
            "type": ntype,
            "attachment_filename": attachment_filename,
            "attachment_original_name": attachment_original_name,
            "attachment_type": attachment_type,
            "created_at": datetime.now(timezone.utc),
        }
        result = db[COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id

        return jsonify({"success": True, "notification": _doc_to_dict(doc)}), 201

    except Exception as exc:
        logger.error("create_notification error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Admin — List all
# ─────────────────────────────────────────────────────────────

@notification_bp.route("/api/admin/notifications", methods=["GET"])
def list_admin_notifications():
    """Return all notifications for admin management (newest first)."""
    try:
        docs = list(db[COLLECTION].find().sort("created_at", -1))
        return jsonify([_doc_to_dict(d) for d in docs])
    except Exception as exc:
        logger.error("list_admin_notifications error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Admin — Delete
# ─────────────────────────────────────────────────────────────

@notification_bp.route("/api/admin/notifications/<notification_id>", methods=["DELETE"])
def delete_notification(notification_id):
    """Delete a notification by id (also removes attached file from disk)."""
    try:
        oid = _as_oid(notification_id)
        if not oid:
            return jsonify({"error": "Invalid notification id"}), 400

        doc = db[COLLECTION].find_one({"_id": oid})
        if not doc:
            return jsonify({"error": "Notification not found"}), 404

        # Remove attachment file from disk if present
        af = doc.get("attachment_filename")
        if af:
            fpath = os.path.join(NOTIF_UPLOAD_DIR, af)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError as e:
                    logger.warning("Could not delete attachment %s: %s", fpath, e)

        db[COLLECTION].delete_one({"_id": oid})
        return jsonify({"success": True})

    except Exception as exc:
        logger.error("delete_notification error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — List (students)
# ─────────────────────────────────────────────────────────────

@notification_bp.route("/api/notifications", methods=["GET"])
def list_public_notifications():
    """Public endpoint: return all notifications newest-first."""
    try:
        docs = list(db[COLLECTION].find().sort("created_at", -1))
        return jsonify([_doc_to_dict(d) for d in docs])
    except Exception as exc:
        logger.error("list_public_notifications error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ─────────────────────────────────────────────────────────────
# Public — Serve attachment file
# ─────────────────────────────────────────────────────────────

@notification_bp.route("/uploads/notifications/<filename>", methods=["GET"])
def serve_notification_attachment(filename):
    """Serve a notification attachment file from storage."""
    try:
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(NOTIF_UPLOAD_DIR, safe_filename)

        if not os.path.isfile(file_path):
            return jsonify({"error": "File not found"}), 404

        ext = os.path.splitext(safe_filename)[1].lower()

        # Determine MIME type and whether to serve inline or as attachment
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        mimetype = mime_map.get(ext, "application/octet-stream")
        # Images and PDFs served inline; DOCX as download
        as_attachment = ext == ".docx"

        return send_file(file_path, mimetype=mimetype, as_attachment=as_attachment)

    except Exception as exc:
        logger.error("serve_notification_attachment error: %s", exc)
        return jsonify({"error": str(exc)}), 500
