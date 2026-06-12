"""
CUI CampusBot - Email Service Module
Sends transactional emails (password reset, notifications) via Gmail SMTP.

Configuration (via environment variables):
    MAIL_SERVER          – SMTP host          (default: smtp.gmail.com)
    MAIL_PORT            – SMTP port          (default: 587)
    MAIL_USE_TLS         – Start TLS?         (default: true)
    MAIL_USERNAME        – Sender address     (e.g. cuicampusbot.admin@gmail.com)
    MAIL_PASSWORD        – App-password       (16-char Google app password)
    MAIL_DEFAULT_SENDER  – Display sender     (default: same as MAIL_USERNAME)
    FRONTEND_BASE_URL    – Base URL for links (default: http://localhost:5000)
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Tuple

logger = logging.getLogger(__name__)

# ── SMTP configuration ──────────────────────────────────────────────
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "") or MAIL_USERNAME
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5000")
ADMIN_INVITE_BASE_URL = os.getenv(
  "ADMIN_INVITE_BASE_URL",
  f"{FRONTEND_BASE_URL.rstrip('/')}/admin/register",
)


def _build_reset_email_html(reset_link: str, expiry_minutes: int) -> str:
    """Return a branded HTML email body for the password-reset message."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#050d14;font-family:'Inter',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050d14;padding:40px 0;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#0d1117;border:2px solid #00ffff;border-radius:12px;padding:32px;">
        <tr><td style="text-align:center;padding-bottom:20px;">
          <h1 style="color:#00ffff;margin:0;font-size:24px;">CUI Campus Bot</h1>
          <p style="color:#9ca3af;font-size:13px;margin:4px 0 0;">Password Reset Request</p>
        </td></tr>
        <tr><td style="color:#e5e7eb;font-size:14px;line-height:1.7;padding:0 8px;">
          <p>Hello,</p>
          <p>We received a request to reset your admin password. Click the button below
             to choose a new password. This link is valid for
             <strong style="color:#00ffff;">{expiry_minutes} minutes</strong>.</p>
        </td></tr>
        <tr><td align="center" style="padding:24px 0;">
          <a href="{reset_link}"
             style="display:inline-block;background:#0b1320;color:#00ffff;
                    border:2px solid #00ffff;border-radius:8px;padding:14px 36px;
                    text-decoration:none;font-weight:700;font-size:15px;
                    box-shadow:0 0 10px rgba(0,255,255,.15);">
            Reset Password
          </a>
        </td></tr>
        <tr><td style="color:#9ca3af;font-size:12px;line-height:1.6;padding:0 8px;">
          <p>If the button doesn't work, copy and paste this URL into your browser:</p>
          <p style="word-break:break-all;color:#00b1a0;">{reset_link}</p>
          <p>If you did not request a password reset, you can safely ignore this email.
             Your password will remain unchanged.</p>
        </td></tr>
        <tr><td style="border-top:1px solid #1f2937;padding-top:16px;text-align:center;">
          <p style="color:#6b7280;font-size:11px;margin:0;">
            &copy; CUI Campus Bot &mdash; COMSATS University Islamabad
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_reset_email_plain(reset_link: str, expiry_minutes: int) -> str:
    """Plain-text body for the password-reset email (matches project spec)."""
    return (
        "Hello,\n\n"
        "We received a request to reset your admin password for CUI Campus Bot.\n\n"
        "Click the link below to reset your password:\n\n"
        f"{reset_link}\n\n"
        f"This link will expire in {expiry_minutes} minutes.\n"
        "If you did not request this, you can ignore this email.\n\n"
        "Regards,\n"
        "CUI Campus Bot\n"
    )


def _build_invite_email_plain(invite_link: str, expiry_hours: int, invited_role: str) -> str:
    """Plain-text body for the admin invitation email."""
    return (
        "Hello,\n\n"
        f"You have been invited to join CUI Campus Bot as an {invited_role}.\n\n"
        "Click the link below to complete your registration:\n\n"
        f"{invite_link}\n\n"
        f"This invitation will expire in {expiry_hours} hours and can only be used once.\n"
        "If you were not expecting this invitation, please ignore this email.\n\n"
        "Regards,\n"
        "CUI Campus Bot\n"
    )


def _build_invite_email_html(invite_link: str, expiry_hours: int, invited_role: str) -> str:
    """Return a branded HTML email body for admin invitation."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#050d14;font-family:'Inter',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#050d14;padding:40px 0;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0"
             style="background:#0d1117;border:2px solid #00ffff;border-radius:12px;padding:32px;">
        <tr><td style="text-align:center;padding-bottom:20px;">
          <h1 style="color:#00ffff;margin:0;font-size:24px;">CUI Campus Bot</h1>
          <p style="color:#9ca3af;font-size:13px;margin:4px 0 0;">Admin Invitation</p>
        </td></tr>
        <tr><td style="color:#e5e7eb;font-size:14px;line-height:1.7;padding:0 8px;">
          <p>Hello,</p>
          <p>You have been invited as an <strong style="color:#00ffff;">{invited_role}</strong>.</p>
          <p>This invitation is valid for <strong style="color:#00ffff;">{expiry_hours} hours</strong> and can be used one time.</p>
        </td></tr>
        <tr><td align="center" style="padding:24px 0;">
          <a href="{invite_link}"
             style="display:inline-block;background:#0b1320;color:#00ffff;
                    border:2px solid #00ffff;border-radius:8px;padding:14px 36px;
                    text-decoration:none;font-weight:700;font-size:15px;
                    box-shadow:0 0 10px rgba(0,255,255,.15);">
            Complete Registration
          </a>
        </td></tr>
        <tr><td style="color:#9ca3af;font-size:12px;line-height:1.6;padding:0 8px;">
          <p>If the button doesn't work, copy and paste this URL into your browser:</p>
          <p style="word-break:break-all;color:#00b1a0;">{invite_link}</p>
          <p>If you did not expect this invitation, you can safely ignore this email.</p>
        </td></tr>
        <tr><td style="border-top:1px solid #1f2937;padding-top:16px;text-align:center;">
          <p style="color:#6b7280;font-size:11px;margin:0;">
            &copy; CUI Campus Bot &mdash; COMSATS University Islamabad
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_reset_email(
    recipient_email: str,
    reset_token: str,
    expiry_minutes: int = 10,
) -> Tuple[bool, str]:
    """
    Send a password-reset email to *recipient_email*.

    Args:
        recipient_email: Where the email goes.
        reset_token:     The plain-text token (will be embedded in the URL).
        expiry_minutes:  How long the link is valid (shown in email text).

    Returns:
        (success: bool, message: str)
    """
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.error("[EMAIL] MAIL_USERNAME or MAIL_PASSWORD not configured")
        return False, "Email service is not configured"

    # Build the reset link
    base = FRONTEND_BASE_URL.rstrip("/")
    reset_link = f"{base}/reset-password?token={reset_token}"

    # Construct MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "CUI Campus Bot - Password Reset"
    msg["From"] = MAIL_DEFAULT_SENDER
    msg["To"] = recipient_email

    plain_body = _build_reset_email_plain(reset_link, expiry_minutes)
    html_body = _build_reset_email_html(reset_link, expiry_minutes)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
            if MAIL_USE_TLS:
                server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_DEFAULT_SENDER, [recipient_email], msg.as_string())

        logger.info(f"[EMAIL] Reset email sent to {recipient_email}")
        return True, "Reset email sent successfully"

    except smtplib.SMTPAuthenticationError:
        logger.error("[EMAIL] SMTP authentication failed – check MAIL_USERNAME / MAIL_PASSWORD")
        return False, "Email authentication failed"
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"[EMAIL] Recipient refused: {recipient_email}")
        return False, "Recipient email address was refused"
    except smtplib.SMTPException as exc:
        logger.error(f"[EMAIL] SMTP error: {exc}")
        return False, f"Email delivery failed: {exc}"
    except Exception as exc:
        logger.error(f"[EMAIL] Unexpected error: {exc}")
        return False, f"Email service error: {exc}"


def send_admin_invite_email(
    recipient_email: str,
    invite_token: str,
    expiry_hours: int = 24,
    invited_role: str = "admin",
) -> Tuple[bool, str]:
    """
    Send an admin invitation email.

    Args:
        recipient_email: Invite recipient.
        invite_token: Plain invitation token.
        expiry_hours: Invite validity window for display.
        invited_role: Target role for invitation.

    Returns:
        (success: bool, message: str)
    """
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.error("[EMAIL] MAIL_USERNAME or MAIL_PASSWORD not configured")
        return False, "Email service is not configured"

    invite_link = f"{ADMIN_INVITE_BASE_URL}?token={invite_token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Admin Invitation"
    msg["From"] = MAIL_DEFAULT_SENDER
    msg["To"] = recipient_email

    plain_body = _build_invite_email_plain(invite_link, expiry_hours, invited_role)
    html_body = _build_invite_email_html(invite_link, expiry_hours, invited_role)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=15) as server:
            if MAIL_USE_TLS:
                server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_DEFAULT_SENDER, [recipient_email], msg.as_string())

        logger.info(f"[EMAIL] Admin invitation sent to {recipient_email}")
        return True, "Invitation email sent successfully"

    except smtplib.SMTPAuthenticationError:
        logger.error("[EMAIL] SMTP authentication failed – check MAIL_USERNAME / MAIL_PASSWORD")
        return False, "Email authentication failed"
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"[EMAIL] Recipient refused: {recipient_email}")
        return False, "Recipient email address was refused"
    except smtplib.SMTPException as exc:
        logger.error(f"[EMAIL] SMTP error: {exc}")
        return False, f"Email delivery failed: {exc}"
    except Exception as exc:
        logger.error(f"[EMAIL] Unexpected error: {exc}")
        return False, f"Email service error: {exc}"
