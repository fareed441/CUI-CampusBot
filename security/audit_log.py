"""
CUI CampusBot - Audit Logging Module
Logs admin actions to MongoDB for accountability and compliance.
Every sensitive operation (login, upload, delete, timetable changes)
is recorded with timestamp, user, IP, and action details.
"""

from datetime import datetime
from functools import wraps
from flask import request
import logging

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    MongoDB-backed audit logger.
    Stores records in the 'audit_log' collection.
    """

    def __init__(self, mongo_db=None):
        self._db = mongo_db

    def set_db(self, mongo_db):
        """Set/update the MongoDB database reference."""
        self._db = mongo_db

    def log(self, action: str, user: str = "system", details: dict = None,
            ip_address: str = None, severity: str = "info"):
        """
        Write an audit log entry.

        Args:
            action: Short description, e.g. 'LOGIN_SUCCESS', 'DOCUMENT_DELETE'
            user: Username/email of the actor
            details: Arbitrary dict with extra context
            ip_address: Client IP (auto-detected if None)
            severity: 'info' | 'warning' | 'critical'
        """
        if ip_address is None:
            try:
                ip_address = request.remote_addr or "unknown"
            except RuntimeError:
                ip_address = "no-request-context"

        entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "user": user,
            "ip_address": ip_address,
            "severity": severity,
            "details": details or {},
        }

        # Persist to MongoDB
        if self._db is not None:
            try:
                self._db.audit_log.insert_one(entry)
            except Exception as exc:
                logger.error(f"[AUDIT] Failed to write audit log: {exc}")

        # Always echo to application log
        log_line = f"[AUDIT] {severity.upper()} | {action} | user={user} | ip={ip_address}"
        if details:
            log_line += f" | {details}"
        if severity == "critical":
            logger.critical(log_line)
        elif severity == "warning":
            logger.warning(log_line)
        else:
            logger.info(log_line)
        print(log_line)

    # ----- Convenience shortcuts -----

    def login_success(self, user: str, **kwargs):
        self.log("LOGIN_SUCCESS", user=user, severity="info", **kwargs)

    def login_failure(self, user: str, reason: str = "", **kwargs):
        self.log("LOGIN_FAILURE", user=user, severity="warning",
                 details={"reason": reason}, **kwargs)

    def document_upload(self, user: str, filename: str, **kwargs):
        self.log("DOCUMENT_UPLOAD", user=user,
                 details={"filename": filename}, **kwargs)

    def document_delete(self, user: str, doc_id: str, **kwargs):
        self.log("DOCUMENT_DELETE", user=user,
                 details={"doc_id": doc_id}, **kwargs)

    def timetable_create(self, user: str, batch: str, **kwargs):
        self.log("TIMETABLE_CREATE", user=user,
                 details={"batch": batch}, **kwargs)

    def timetable_update(self, user: str, entry_id: str, **kwargs):
        self.log("TIMETABLE_UPDATE", user=user,
                 details={"entry_id": entry_id}, **kwargs)

    def timetable_delete(self, user: str, entry_id: str, **kwargs):
        self.log("TIMETABLE_DELETE", user=user,
                 details={"entry_id": entry_id}, **kwargs)

    def timetable_generate(self, user: str, **kwargs):
        self.log("TIMETABLE_GENERATE", user=user, **kwargs)

    def timetable_excel_upload(self, user: str, filename: str, **kwargs):
        self.log("TIMETABLE_EXCEL_UPLOAD", user=user,
                 details={"filename": filename}, **kwargs)

    def admin_unlock(self, ip: str, **kwargs):
        self.log("ADMIN_UNLOCK", user="session", ip_address=ip, **kwargs)

    def admin_lock(self, ip: str, **kwargs):
        self.log("ADMIN_LOCK", user="session", ip_address=ip, **kwargs)

    def password_reset_request(self, email: str, **kwargs):
        self.log("PASSWORD_RESET_REQUEST", user=email, severity="info", **kwargs)

    def password_reset_email_sent(self, email: str, **kwargs):
        self.log("PASSWORD_RESET_EMAIL_SENT", user=email, severity="info", **kwargs)

    def password_reset_email_failed(self, email: str, reason: str = "", **kwargs):
        self.log("PASSWORD_RESET_EMAIL_FAILED", user=email, severity="warning",
                 details={"reason": reason}, **kwargs)

    def password_reset_complete(self, email: str, **kwargs):
        self.log("PASSWORD_RESET_COMPLETE", user=email, severity="info", **kwargs)

    def password_reset_failed(self, email: str, reason: str = "", **kwargs):
        self.log("PASSWORD_RESET_FAILED", user=email, severity="warning",
                 details={"reason": reason}, **kwargs)

    def password_reset_invalid_token(self, ip_address: str = "unknown", **kwargs):
        self.log("PASSWORD_RESET_INVALID_TOKEN", user="anonymous", severity="warning",
                 ip_address=ip_address, **kwargs)

    def role_change(self, admin_user: str, target_user: str, new_role: str, **kwargs):
        self.log("ROLE_CHANGE", user=admin_user, severity="warning",
                 details={"target_user": target_user, "new_role": new_role}, **kwargs)

    def user_deactivated(self, admin_user: str, target_user: str, **kwargs):
        self.log("USER_DEACTIVATED", user=admin_user, severity="warning",
                 details={"target_user": target_user}, **kwargs)


# Global singleton — initialized once, shared across the app
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Return the global AuditLogger instance."""
    return audit_logger
