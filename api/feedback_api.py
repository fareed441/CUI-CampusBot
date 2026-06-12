"""
CUI CampusBot - Feedback API Module
Handles public student feedback submission and admin feedback management.
"""

import hashlib
import re
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from bson import ObjectId
from security.input_validation import sanitize_string, validate_email, validate_batch_code

feedback_bp = Blueprint('feedback', __name__)

# =============================================
# Constants
# =============================================

ALLOWED_MODULES = {"Chatbot", "Timetable", "General"}
ALLOWED_CATEGORIES = {
    "Bug Report", "Suggestion", "Complaint",
    "UI/UX Issue", "Wrong Timetable", "Chatbot Wrong Answer", "Other"
}
ALLOWED_STATUSES = {"new", "in_review", "resolved", "rejected"}

MESSAGE_MIN_LENGTH = 10
MESSAGE_MAX_LENGTH = 1000
DUPLICATE_WINDOW_MINUTES = 10

# =============================================
# Helpers
# =============================================

def _get_db():
    """Get the MongoDB database reference from the Flask app."""
    from flask import current_app
    return current_app.config.get('MONGO_DB')


def _get_audit():
    """Get the audit logger."""
    from security.audit_log import get_audit_logger
    return get_audit_logger()


def _hash_ip(ip: str) -> str:
    """SHA-256 hash of an IP address for abuse tracking."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode('utf-8')).hexdigest()


def _normalize_batch(batch: str) -> str:
    """Normalize a batch code: trim, uppercase, standardize separators."""
    if not batch:
        return ""
    batch = batch.strip().upper()
    # Replace multiple hyphens/underscores/spaces with single hyphen
    batch = re.sub(r'[\s_]+', '-', batch)
    batch = re.sub(r'-{2,}', '-', batch)
    return batch


def _validate_feedback_input(data: dict) -> tuple:
    """
    Validate public feedback submission data.
    Returns (is_valid: bool, error_message: str, cleaned_data: dict).
    """
    errors = []

    # Required: batch_section
    batch_section = _normalize_batch(data.get('batch_section', ''))
    if not batch_section:
        errors.append("Please enter a valid batch code.")
    else:
        valid_batch, batch_err = validate_batch_code(batch_section)
        if not valid_batch:
            errors.append("Please enter a valid batch code (e.g. FA22-BCS-8A).")

    # Required: module
    module = (data.get('module') or '').strip()
    if module not in ALLOWED_MODULES:
        errors.append(f"Module must be one of: {', '.join(sorted(ALLOWED_MODULES))}.")

    # Required: category
    category = (data.get('category') or '').strip()
    if category not in ALLOWED_CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}.")

    # Required: rating (1-5)
    try:
        rating = int(data.get('rating', 0))
        if rating < 1 or rating > 5:
            errors.append("Rating must be between 1 and 5.")
    except (ValueError, TypeError):
        errors.append("Rating must be a number between 1 and 5.")
        rating = 0

    # Required: message
    message = (data.get('message') or '').strip()
    if not message or len(message) < MESSAGE_MIN_LENGTH:
        errors.append(f"Please enter a clear message with at least {MESSAGE_MIN_LENGTH} characters.")
    elif len(message) > MESSAGE_MAX_LENGTH:
        errors.append(f"Message is too long (max {MESSAGE_MAX_LENGTH} characters).")

    # Optional: email (validate format if provided)
    email = (data.get('email') or '').strip()
    if email:
        valid_email, email_err = validate_email(email)
        if not valid_email:
            errors.append("Please enter a valid email address.")

    # Optional: name
    name = (data.get('name') or '').strip()

    # Honeypot check
    honeypot = (data.get('website') or '').strip()
    if honeypot:
        # Bot detected - silently flag
        return False, "__honeypot__", {}

    # Page context (optional)
    page_context = (data.get('page_context') or '').strip()[:50]

    if errors:
        return False, errors[0], {}

    cleaned = {
        'name': sanitize_string(name, 100),
        'email': email.lower() if email else '',
        'batch_section': batch_section,
        'module': module,
        'category': category,
        'rating': rating,
        'message': sanitize_string(message, MESSAGE_MAX_LENGTH),
        'page_context': sanitize_string(page_context, 50),
    }
    return True, '', cleaned


def _check_duplicate(db, batch_section: str, module: str, message: str) -> bool:
    """Check if a similar feedback was submitted recently."""
    if db is None:
        return False
    cutoff = datetime.utcnow() - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    existing = db.feedback.find_one({
        'batch_section': batch_section,
        'module': module,
        'message': message,
        'created_at': {'$gte': cutoff}
    })
    return existing is not None


# =============================================
# PUBLIC ROUTES
# =============================================

@feedback_bp.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """
    Public endpoint for student feedback submission.
    Rate limited: 3 per 10 minutes per IP (applied in app.py).
    """
    db = _get_db()
    if db is None:
        return jsonify({'success': False, 'message': 'Service temporarily unavailable.'}), 503

    data = request.json or {}

    # Validate input
    is_valid, error, cleaned = _validate_feedback_input(data)

    if not is_valid:
        if error == "__honeypot__":
            # Silently accept but mark as spam
            spam_doc = {
                'name': sanitize_string((data.get('name') or ''), 100),
                'email': (data.get('email') or '').strip().lower(),
                'batch_section': _normalize_batch(data.get('batch_section', '')),
                'module': (data.get('module') or '').strip(),
                'category': (data.get('category') or '').strip(),
                'rating': 0,
                'message': sanitize_string((data.get('message') or ''), MESSAGE_MAX_LENGTH),
                'status': 'new',
                'admin_note': '',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'resolved_at': None,
                'ip_hash': _hash_ip(request.remote_addr),
                'user_agent': sanitize_string(request.headers.get('User-Agent', ''), 300),
                'page_context': '',
                'is_spam': True,
            }
            try:
                db.feedback.insert_one(spam_doc)
            except Exception:
                pass
            # Return success to not alert the bot
            return jsonify({
                'success': True,
                'message': 'Thank you. Your feedback has been submitted successfully.'
            })
        return jsonify({'success': False, 'message': error}), 400

    # Duplicate detection
    if _check_duplicate(db, cleaned['batch_section'], cleaned['module'], cleaned['message']):
        return jsonify({
            'success': False,
            'message': 'You have recently submitted similar feedback. Please wait before submitting again.'
        }), 429

    # Build document
    now = datetime.utcnow()
    feedback_doc = {
        'name': cleaned['name'],
        'email': cleaned['email'],
        'batch_section': cleaned['batch_section'],
        'module': cleaned['module'],
        'category': cleaned['category'],
        'rating': cleaned['rating'],
        'message': cleaned['message'],
        'status': 'new',
        'admin_note': '',
        'created_at': now,
        'updated_at': now,
        'resolved_at': None,
        'ip_hash': _hash_ip(request.remote_addr),
        'user_agent': sanitize_string(request.headers.get('User-Agent', ''), 300),
        'page_context': cleaned['page_context'],
        'is_spam': False,
    }

    try:
        db.feedback.insert_one(feedback_doc)
        return jsonify({
            'success': True,
            'message': 'Thank you. Your feedback has been submitted successfully.'
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Feedback insert failed: {e}")
        return jsonify({'success': False, 'message': 'Failed to submit feedback. Please try again.'}), 500


# =============================================
# ADMIN ROUTES
# =============================================

@feedback_bp.route('/api/admin/feedback', methods=['GET'])
def get_feedback_list():
    """
    Admin-only: Return paginated feedback list with filters.
    Protected by admin_required decorator applied in app.py.
    """
    db = _get_db()
    if db is None:
        return jsonify({'feedbacks': [], 'total': 0, 'page': 1, 'pages': 1})

    # Pagination
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(100, max(1, int(request.args.get('per_page', 20))))
    except (ValueError, TypeError):
        per_page = 20

    # Build filter query
    query = {}

    status = request.args.get('status', '').strip()
    if status and status in ALLOWED_STATUSES:
        query['status'] = status

    module = request.args.get('module', '').strip()
    if module and module in ALLOWED_MODULES:
        query['module'] = module

    category = request.args.get('category', '').strip()
    if category and category in ALLOWED_CATEGORIES:
        query['category'] = category

    batch = request.args.get('batch_section', '').strip().upper()
    if batch:
        query['batch_section'] = {'$regex': re.escape(batch), '$options': 'i'}

    rating = request.args.get('rating', '').strip()
    if rating:
        try:
            query['rating'] = int(rating)
        except ValueError:
            pass

    is_spam = request.args.get('is_spam', '').strip().lower()
    if is_spam == 'true':
        query['is_spam'] = True
    elif is_spam == 'false':
        query['is_spam'] = False
    else:
        # By default, hide spam
        query['is_spam'] = {'$ne': True}

    # Date range
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if date_from or date_to:
        date_query = {}
        if date_from:
            try:
                date_query['$gte'] = datetime.fromisoformat(date_from)
            except ValueError:
                pass
        if date_to:
            try:
                date_query['$lte'] = datetime.fromisoformat(date_to) + timedelta(days=1)
            except ValueError:
                pass
        if date_query:
            query['created_at'] = date_query

    try:
        total = db.feedback.count_documents(query)
        total_pages = max(1, (total + per_page - 1) // per_page)

        feedbacks = list(
            db.feedback.find(query)
            .sort('created_at', -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )

        result = []
        for fb in feedbacks:
            result.append({
                'id': str(fb['_id']),
                'name': fb.get('name', ''),
                'email': fb.get('email', ''),
                'batch_section': fb.get('batch_section', ''),
                'module': fb.get('module', ''),
                'category': fb.get('category', ''),
                'rating': fb.get('rating', 0),
                'message': fb.get('message', ''),
                'status': fb.get('status', 'new'),
                'admin_note': fb.get('admin_note', ''),
                'created_at': fb['created_at'].isoformat() if fb.get('created_at') else None,
                'updated_at': fb['updated_at'].isoformat() if fb.get('updated_at') else None,
                'resolved_at': fb['resolved_at'].isoformat() if fb.get('resolved_at') else None,
                'page_context': fb.get('page_context', ''),
                'is_spam': fb.get('is_spam', False),
            })

        # Summary stats
        pipeline = [
            {'$match': {'is_spam': {'$ne': True}}},
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'new_count': {'$sum': {'$cond': [{'$eq': ['$status', 'new']}, 1, 0]}},
                'in_review_count': {'$sum': {'$cond': [{'$eq': ['$status', 'in_review']}, 1, 0]}},
                'resolved_count': {'$sum': {'$cond': [{'$eq': ['$status', 'resolved']}, 1, 0]}},
                'rejected_count': {'$sum': {'$cond': [{'$eq': ['$status', 'rejected']}, 1, 0]}},
                'avg_rating': {'$avg': '$rating'},
                'chatbot_count': {'$sum': {'$cond': [{'$eq': ['$module', 'Chatbot']}, 1, 0]}},
                'timetable_count': {'$sum': {'$cond': [{'$eq': ['$module', 'Timetable']}, 1, 0]}},
            }}
        ]
        summary_result = list(db.feedback.aggregate(pipeline))
        summary = {}
        if summary_result:
            s = summary_result[0]
            summary = {
                'total': s.get('total', 0),
                'new': s.get('new_count', 0),
                'in_review': s.get('in_review_count', 0),
                'resolved': s.get('resolved_count', 0),
                'rejected': s.get('rejected_count', 0),
                'avg_rating': round(s.get('avg_rating', 0) or 0, 1),
                'chatbot': s.get('chatbot_count', 0),
                'timetable': s.get('timetable_count', 0),
            }

        return jsonify({
            'feedbacks': result,
            'total': total,
            'page': page,
            'pages': total_pages,
            'summary': summary,
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Feedback list failed: {e}")
        return jsonify({'feedbacks': [], 'total': 0, 'page': 1, 'pages': 1}), 500


@feedback_bp.route('/api/admin/feedback/<feedback_id>', methods=['GET'])
def get_feedback_detail(feedback_id):
    """Admin-only: Return full detail of one feedback item."""
    db = _get_db()
    if db is None:
        return jsonify({'detail': 'Service unavailable'}), 503

    try:
        fb = db.feedback.find_one({'_id': ObjectId(feedback_id)})
        if not fb:
            return jsonify({'detail': 'Feedback not found'}), 404

        return jsonify({
            'id': str(fb['_id']),
            'name': fb.get('name', ''),
            'email': fb.get('email', ''),
            'batch_section': fb.get('batch_section', ''),
            'module': fb.get('module', ''),
            'category': fb.get('category', ''),
            'rating': fb.get('rating', 0),
            'message': fb.get('message', ''),
            'status': fb.get('status', 'new'),
            'admin_note': fb.get('admin_note', ''),
            'created_at': fb['created_at'].isoformat() if fb.get('created_at') else None,
            'updated_at': fb['updated_at'].isoformat() if fb.get('updated_at') else None,
            'resolved_at': fb['resolved_at'].isoformat() if fb.get('resolved_at') else None,
            'page_context': fb.get('page_context', ''),
            'is_spam': fb.get('is_spam', False),
            'ip_hash': fb.get('ip_hash', ''),
            'user_agent': fb.get('user_agent', ''),
        })
    except Exception as e:
        return jsonify({'detail': 'Invalid feedback ID'}), 400


@feedback_bp.route('/api/admin/feedback/<feedback_id>/status', methods=['PUT'])
def update_feedback_status(feedback_id):
    """
    Admin-only: Update feedback status and optional admin note.
    Logs the change in audit_log.
    """
    db = _get_db()
    if db is None:
        return jsonify({'detail': 'Service unavailable'}), 503

    data = request.json or {}
    new_status = (data.get('status') or '').strip()
    admin_note = (data.get('admin_note') or '').strip()

    if new_status not in ALLOWED_STATUSES:
        return jsonify({'detail': f'Status must be one of: {", ".join(sorted(ALLOWED_STATUSES))}'}), 400

    try:
        fb = db.feedback.find_one({'_id': ObjectId(feedback_id)})
        if not fb:
            return jsonify({'detail': 'Feedback not found'}), 404

        old_status = fb.get('status', 'new')
        now = datetime.utcnow()

        update_fields = {
            'status': new_status,
            'updated_at': now,
        }
        if admin_note:
            update_fields['admin_note'] = sanitize_string(admin_note, 1000)

        # Set resolved_at when status becomes resolved
        if new_status == 'resolved' and old_status != 'resolved':
            update_fields['resolved_at'] = now
        elif new_status != 'resolved':
            update_fields['resolved_at'] = None

        db.feedback.update_one(
            {'_id': ObjectId(feedback_id)},
            {'$set': update_fields}
        )

        # Audit log
        audit = _get_audit()
        admin_user = 'admin'
        if hasattr(request, 'user') and request.user:
            admin_user = request.user.get('sub', 'admin')

        audit.log(
            action='FEEDBACK_STATUS_UPDATE',
            user=admin_user,
            details={
                'feedback_id': feedback_id,
                'old_status': old_status,
                'new_status': new_status,
                'admin_note': admin_note[:200] if admin_note else '',
            },
            ip_address=request.remote_addr,
        )

        return jsonify({
            'success': True,
            'message': f'Feedback status updated to {new_status}.'
        })
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Feedback status update failed: {e}")
        return jsonify({'detail': 'Failed to update feedback'}), 500


@feedback_bp.route('/api/admin/feedback/<feedback_id>/spam', methods=['PUT'])
def toggle_feedback_spam(feedback_id):
    """Admin-only: Mark or unmark feedback as spam."""
    db = _get_db()
    if db is None:
        return jsonify({'detail': 'Service unavailable'}), 503

    data = request.json or {}
    is_spam = bool(data.get('is_spam', True))

    try:
        fb = db.feedback.find_one({'_id': ObjectId(feedback_id)})
        if not fb:
            return jsonify({'detail': 'Feedback not found'}), 404

        db.feedback.update_one(
            {'_id': ObjectId(feedback_id)},
            {'$set': {
                'is_spam': is_spam,
                'updated_at': datetime.utcnow(),
            }}
        )

        # Audit log
        audit = _get_audit()
        admin_user = 'admin'
        if hasattr(request, 'user') and request.user:
            admin_user = request.user.get('sub', 'admin')

        audit.log(
            action='FEEDBACK_SPAM_TOGGLE',
            user=admin_user,
            details={
                'feedback_id': feedback_id,
                'is_spam': is_spam,
            },
            ip_address=request.remote_addr,
        )

        return jsonify({
            'success': True,
            'message': f'Feedback {"marked as spam" if is_spam else "unmarked as spam"}.'
        })
    except Exception as e:
        return jsonify({'detail': 'Failed to update feedback'}), 500
