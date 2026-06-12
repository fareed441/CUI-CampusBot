"""
CUI CampusBot - Input Validation Module
Server-side validation for all user inputs.
Prevents injection, enforces formats, and sanitizes data.
"""

import os
import re
import html
from typing import Optional, Tuple

# =============================================
# Batch Code Validation
# =============================================

# Allowed format: DEPT-SEMESTER-NUMBER  e.g. BCS-FA25-2A, FA22-BCS-8A
BATCH_CODE_PATTERN = re.compile(
    r'^[A-Z]{2,5}-(?:FA|SP)\d{2}-\d{1,2}[A-Z]?$|'
    r'^(?:FA|SP)\d{2}-[A-Z]{2,5}-\d{1,2}[A-Z]?$',
    re.IGNORECASE,
)


def validate_batch_code(batch_code: str) -> Tuple[bool, str]:
    """
    Validate a timetable batch code.
    Returns (is_valid, error_message).
    """
    if not batch_code or not batch_code.strip():
        return False, "Batch code is required"

    code = batch_code.strip()
    if len(code) > 30:
        return False, "Batch code is too long (max 30 chars)"

    if not BATCH_CODE_PATTERN.match(code):
        return False, "Invalid batch code format. Expected e.g. BCS-FA25-2A or FA22-BCS-8A"

    return True, ""


# =============================================
# Email Validation
# =============================================

EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate an email address."""
    if not email or not email.strip():
        return False, "Email is required"

    email = email.strip()
    if len(email) > 254:
        return False, "Email is too long"

    if not EMAIL_PATTERN.match(email):
        return False, "Invalid email format"

    return True, ""


# =============================================
# Password Validation
# =============================================

# Common weak passwords that should be rejected
WEAK_PASSWORDS = {
    "password", "password123", "123456", "12345678", "123456789",
    "qwerty", "abc123", "password1", "admin", "admin123",
    "admin123456", "letmein", "welcome", "monkey", "dragon",
    "master", "login", "princess", "football", "shadow",
    "sunshine", "trustno1", "iloveyou", "batman", "access",
    "hello", "charlie", "donald", "password123!", "changeme",
    "your-super-secret-key-change-in-production",
}

# Load extended common passwords from file (if it exists)
_COMMON_PASSWORDS_FILE = os.path.join(
    os.path.dirname(__file__), "common_passwords.txt"
)
if os.path.isfile(_COMMON_PASSWORDS_FILE):
    try:
        with open(_COMMON_PASSWORDS_FILE, "r", encoding="utf-8") as _f:
            for _line in _f:
                _pw = _line.strip()
                if _pw and not _pw.startswith("#"):
                    WEAK_PASSWORDS.add(_pw.lower())
    except Exception:
        pass  # file read failure is non-fatal

WEAK_PASSWORDS = frozenset(WEAK_PASSWORDS)


def validate_password(password: str, min_length: int = 12) -> Tuple[bool, str]:
    """
    Validate a password against security policy.

    Policy:
    - Minimum 12 characters
    - Maximum 64 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    - Not in the common weak passwords list
    - No silent trimming
    """
    if not password:
        return False, "Password is required"

    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters"

    if len(password) > 64:
        return False, "Password is too long (max 64 characters)"

    if password.lower() in WEAK_PASSWORDS:
        return False, "This password is too common. Choose a stronger password."

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least 1 uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least 1 lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least 1 digit"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\\/~`]', password):
        return False, "Password must contain at least 1 special character"

    return True, ""


# =============================================
# Role Validation
# =============================================

VALID_ROLES = frozenset({
    "admin", "user", "super_admin",
    "hod_cs", "hod_se", "timetable_coordinator",
})


def validate_role(role: str) -> Tuple[bool, str]:
    """Validate a user role string."""
    if not role or not role.strip():
        return False, "Role is required"

    if role.strip().lower() not in VALID_ROLES:
        return False, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}"

    return True, ""


# =============================================
# Feedback Validation
# =============================================

def validate_feedback(subject: str, message: str,
                      feedback_type: str = "general") -> Tuple[bool, str]:
    """Validate feedback submission fields."""
    valid_types = {"general", "bug", "suggestion", "complaint"}

    if feedback_type not in valid_types:
        return False, f"Invalid feedback type. Must be one of: {', '.join(sorted(valid_types))}"

    if not subject or len(subject.strip()) < 3:
        return False, "Subject must be at least 3 characters"

    if len(subject) > 200:
        return False, "Subject is too long (max 200 characters)"

    if not message or len(message.strip()) < 10:
        return False, "Message must be at least 10 characters"

    if len(message) > 2000:
        return False, "Message is too long (max 2000 characters)"

    return True, ""


# =============================================
# File Upload Validation
# =============================================

ALLOWED_DOCUMENT_EXTENSIONS = frozenset({'pdf', 'doc', 'docx', 'txt', 'json', 'csv'})
ALLOWED_TIMETABLE_EXTENSIONS = frozenset({'xlsx', 'xls', 'csv'})
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def validate_file_upload(filename: str, file_size: int,
                         allowed_extensions: frozenset = None) -> Tuple[bool, str]:
    """
    Validate an uploaded file.

    Args:
        filename: Original filename
        file_size: Size in bytes
        allowed_extensions: Set of allowed extensions (defaults to document types)
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_DOCUMENT_EXTENSIONS

    if not filename or not filename.strip():
        return False, "Filename is required"

    # Extract extension
    if '.' not in filename:
        return False, "File must have an extension"

    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed_extensions:
        return False, f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(allowed_extensions))}"

    # Check for double extensions (e.g. file.php.pdf)
    parts = filename.split('.')
    if len(parts) > 2:
        # Allow compound extensions like .tar.gz but flag suspicious ones
        suspicious_exts = {'php', 'exe', 'sh', 'bat', 'cmd', 'ps1', 'js', 'py'}
        for part in parts[:-1]:
            if part.lower() in suspicious_exts:
                return False, "Suspicious file extension detected"

    if file_size > MAX_FILE_SIZE_BYTES:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB"

    if file_size == 0:
        return False, "File is empty"

    return True, ""


# =============================================
# General Sanitization
# =============================================

def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Sanitize a user-provided string:
    - Strip whitespace
    - HTML-escape special characters
    - Truncate to max_length
    """
    if not isinstance(value, str):
        return ""
    value = value.strip()
    value = html.escape(value, quote=True)
    return value[:max_length]


def sanitize_search_query(query: str) -> str:
    """Sanitize a search query to prevent MongoDB injection."""
    if not isinstance(query, str):
        return ""
    # Remove MongoDB operators
    sanitized = re.sub(r'\$\w+', '', query)
    # Remove braces used in injection
    sanitized = sanitized.replace('{', '').replace('}', '')
    return sanitized.strip()[:500]


# =============================================
# Chat Message Validation
# =============================================

def validate_chat_message(message: str) -> Tuple[bool, str]:
    """Validate a chat message."""
    if not message or not message.strip():
        return False, "Message is required"

    if len(message.strip()) > 2000:
        return False, "Message is too long (max 2000 characters)"

    if len(message.strip()) < 1:
        return False, "Message cannot be empty"

    return True, ""


# =============================================
# Timetable Entry Validation
# =============================================

def validate_timetable_entry(data: dict) -> Tuple[bool, str]:
    """Validate a timetable entry dict."""
    required_fields = ['batch_section', 'course', 'teacher', 'day', 'slotStart']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            return False, f"Missing required field: {field}"

    # Validate day (0-4 for Mon-Fri)
    try:
        day = int(data['day'])
        if day < 0 or day > 4:
            return False, "Day must be between 0 (Monday) and 4 (Friday)"
    except (ValueError, TypeError):
        return False, "Day must be a valid integer"

    # Validate slotStart (1-6)
    try:
        slot = int(data['slotStart'])
        if slot < 1 or slot > 6:
            return False, "Slot must be between 1 and 6"
    except (ValueError, TypeError):
        return False, "Slot must be a valid integer"

    # Validate slotSpan if present
    if 'slotSpan' in data:
        try:
            span = int(data['slotSpan'])
            if span < 1 or span > 3:
                return False, "Slot span must be between 1 and 3"
        except (ValueError, TypeError):
            return False, "Slot span must be a valid integer"

    # Validate type
    valid_types = {'LEC', 'LAB', 'TUT'}
    entry_type = str(data.get('type', 'LEC')).upper()
    if entry_type not in valid_types:
        return False, f"Type must be one of: {', '.join(valid_types)}"

    # Validate course name length
    if len(str(data['course'])) > 100:
        return False, "Course name too long (max 100 chars)"

    # Validate teacher name length
    if len(str(data['teacher'])) > 100:
        return False, "Teacher name too long (max 100 chars)"

    return True, ""
