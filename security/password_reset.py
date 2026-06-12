"""
CUI CampusBot - Password Reset Module
Implements forgot-password / reset-password flow using
hashed tokens stored in MongoDB with TTL expiry.

Token record schema (password_reset_tokens collection):
    email          – user's email
    user_id        – ObjectId of the user document
    token_hash     – SHA-256 hex digest (never store plaintext)
    created_at     – UTC datetime
    expires_at     – UTC datetime (TTL index auto-deletes)
    used           – bool
    used_at        – UTC datetime | None
    requested_ip   – client IP that requested the reset
"""

import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Tuple
import bcrypt
import logging
from security.input_validation import validate_password

logger = logging.getLogger(__name__)

# Token validity (configurable via env, default 10 min)
RESET_TOKEN_EXPIRY_MINUTES = int(os.getenv("RESET_TOKEN_EXP_MINUTES", "10"))


def _hash_token(token: str) -> str:
    """Hash a reset token with SHA-256 for safe storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_indexes(mongo_db) -> None:
    """Create required indexes once (idempotent). Called at startup."""
    if mongo_db is None:
        return
    try:
        mongo_db.password_reset_tokens.create_index(
            "expires_at", expireAfterSeconds=0
        )
        mongo_db.password_reset_tokens.create_index("email")
        mongo_db.password_reset_tokens.create_index("token_hash")
    except Exception:
        pass  # indexes may already exist


def create_reset_token(
    mongo_db, email: str, requested_ip: str = "unknown"
) -> Tuple[bool, str, str, str]:
    """
    Generate a password-reset token for the given admin email.

    Returns:
        (success, raw_token_or_empty, user_facing_message, recovery_email)
        raw_token is only non-empty when a valid admin user was found.
        recovery_email is the address to send the reset email to.
    """
    GENERIC_MSG = (
        "If an account with that email exists, a password-reset link "
        "has been sent."
    )

    if mongo_db is None:
        return False, "", "Database not available", ""

    # Lookup user — only admins can reset
    user = mongo_db.users.find_one({"email": email})
    if not user:
        logger.info(f"[RESET] Token requested for unknown email: {email}")
        return True, "", GENERIC_MSG, ""

    user_role = user.get("role", "user")
    if user_role not in ("admin", "super_admin"):
        logger.info(f"[RESET] Non-admin reset attempt blocked: {email} (role={user_role})")
        return True, "", GENERIC_MSG, ""  # same generic msg — don't reveal role info

    # Invalidate any previous tokens for this email
    mongo_db.password_reset_tokens.delete_many({"email": email})

    # Generate token
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)

    # Store hashed token with enriched fields
    mongo_db.password_reset_tokens.insert_one({
        "email": email,
        "user_id": user["_id"],
        "token_hash": token_hash,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES),
        "used": False,
        "used_at": None,
        "requested_ip": requested_ip,
    })

    # Ensure TTL + lookup indexes exist
    ensure_indexes(mongo_db)

    # Determine recovery email: use recovery_email field if present, else login email
    recovery = user.get("recovery_email", email)

    logger.info(f"[RESET] Token created for {email} -> send to {recovery} (ip={requested_ip})")
    return True, raw_token, GENERIC_MSG, recovery


def verify_and_reset_password(
    mongo_db, token: str, new_password: str
) -> Tuple[bool, str, str]:
    """
    Verify a reset token and update the user's password.

    Now accepts only the token (no email required) — the token
    is looked up by its hash, and the associated email is resolved.

    Returns:
        (success: bool, message: str, email: str)
        email is returned so the caller can log it, empty on failure.
    """
    if mongo_db is None:
        return False, "Database not available", ""

    valid_password, password_error = validate_password(new_password)
    if not valid_password:
        return False, password_error, ""

    token_hash = _hash_token(token)

    # Find valid, unused token (by hash only)
    record = mongo_db.password_reset_tokens.find_one({
        "token_hash": token_hash,
        "used": False,
    })

    if not record:
        return False, "This password reset link is invalid or has already been used.", ""

    # Check expiry
    if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
        # Mark as used so it cannot be retried
        mongo_db.password_reset_tokens.update_one(
            {"_id": record["_id"]},
            {"$set": {"used": True, "used_at": datetime.utcnow()}},
        )
        return False, "This password reset link has expired. Please request a new one.", ""

    email = record["email"]

    # Hash new password
    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    # Update user's password
    result = mongo_db.users.update_one(
        {"email": email},
        {"$set": {
            "password_hash": password_hash,
            "password_changed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }},
    )

    if result.modified_count == 0:
        return False, "User not found", ""

    # Mark token as used (with timestamp) — TTL index auto-cleans later
    mongo_db.password_reset_tokens.update_one(
        {"_id": record["_id"]},
        {"$set": {"used": True, "used_at": datetime.utcnow()}},
    )

    # Invalidate any other outstanding tokens for this email
    mongo_db.password_reset_tokens.update_many(
        {"email": email, "used": False, "_id": {"$ne": record["_id"]}},
        {"$set": {"used": True, "used_at": datetime.utcnow()}},
    )

    logger.info(f"[RESET] Password reset completed for {email}")
    return True, "Password reset successful. Please log in again.", email


def validate_reset_token(mongo_db, token: str) -> dict:
    """
    Validate a raw reset token without consuming it.

    Returns a dict:
        {"valid": bool, "reason": str, "message": str}
    reason is one of: "missing", "invalid_or_used", "expired", or "" (valid).
    """
    if not token or not token.strip():
        return {
            "valid": False,
            "reason": "missing",
            "message": "Reset token is missing.",
        }

    if mongo_db is None:
        return {
            "valid": False,
            "reason": "invalid_or_used",
            "message": "Database not available.",
        }

    token_hash = _hash_token(token.strip())

    record = mongo_db.password_reset_tokens.find_one({"token_hash": token_hash})

    if not record:
        return {
            "valid": False,
            "reason": "invalid_or_used",
            "message": "This password reset link is invalid or has already been used.",
        }

    if record.get("used"):
        return {
            "valid": False,
            "reason": "invalid_or_used",
            "message": "This password reset link is invalid or has already been used.",
        }

    if record.get("expires_at") and record["expires_at"] < datetime.utcnow():
        return {
            "valid": False,
            "reason": "expired",
            "message": "This password reset link has expired. Please request a new one.",
        }

    return {
        "valid": True,
        "reason": "",
        "message": "Token is valid.",
    }
