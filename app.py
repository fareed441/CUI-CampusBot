"""
Flask Web Application for CUI Campus Chatbot
Serves the web interface and handles API requests
WITH OAuth2-style authentication for Admin access
USES MongoDB Atlas for user authentication
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, session, redirect, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
import jwt
import bcrypt
import hashlib
import certifi
import logging
from pymongo import MongoClient
from bson import ObjectId
from gridfs import GridFS
from gridfs.errors import NoFile
import base64
from rag_pipeline_free import FreeRAGPipeline
from api.pdf_timetable_service import PDFProcessingError, process_master_timetable_pdf
from api.pdf_timetable_store import get_timetable_record, normalize_class_code
from security.audit_log import get_audit_logger
from security.input_validation import (
    validate_email, validate_password, validate_feedback,
    validate_file_upload, validate_chat_message,
    sanitize_string, ALLOWED_DOCUMENT_EXTENSIONS,
)
from security.password_reset import create_reset_token, verify_and_reset_password, validate_reset_token, RESET_TOKEN_EXPIRY_MINUTES
from security.email_service import send_reset_email, send_admin_invite_email
from config import (
    DATA_DIRECTORY,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    RETRIEVAL_TOP_K,
    SYSTEM_PROMPT,
    LLM_PROVIDER,
    PPLX_MODEL,
    get_system_prompt,
    get_language_instruction
)
from routes.timetable_routes import timetable_bp
from routes.notification_routes import notification_bp


def _sanitize_content_disposition_filename(file_name: str) -> str:
    """Sanitize filename for safe use in Content-Disposition header."""
    return (file_name or "document").replace('"', "")


def _parse_single_byte_range(range_header: str, file_size: int):
    """
    Parse a single HTTP byte range.
    Returns (start, end) or None if range is invalid/unsupported.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None

    range_spec = range_header[len("bytes="):].strip()
    if not range_spec or "," in range_spec:
        # Multiple ranges are intentionally unsupported.
        return None

    try:
        start_str, end_str = range_spec.split("-", 1)
    except ValueError:
        return None

    try:
        if start_str == "":
            # Suffix range: bytes=-N
            suffix_len = int(end_str)
            if suffix_len <= 0:
                return None
            start = max(file_size - suffix_len, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            if start < 0:
                return None
            end = file_size - 1 if end_str == "" else int(end_str)

        if end < start or end >= file_size:
            return None

        return start, end
    except ValueError:
        return None


BYTES_IN_MB = 1024 * 1024
ATLAS_STORAGE_LIMIT_MB = 512.0


def _coerce_file_size_bytes(value):
    """Normalize file size values to non-negative integer bytes."""
    if value is None:
        return None

    try:
        normalized = int(value)
        if normalized < 0:
            return None
        return normalized
    except (TypeError, ValueError):
        return None


def _bytes_to_mb(byte_size: int) -> float:
    """Convert bytes to MB rounded to 2 decimal places."""
    return round((byte_size or 0) / BYTES_IN_MB, 2)


def _hash_invite_token(token: str) -> str:
    """Hash admin invite tokens before persistence."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*")}})



# ---- Flask-Limiter (IP-based rate limiting) ----
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],            # no global limit — apply per endpoint
    storage_uri="memory://",      # in-memory; swap to redis:// for multi-worker
)

# ---- JWT Configuration (enforce strong secret) ----
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY or JWT_SECRET_KEY == "your-super-secret-key-change-in-production":
    # Auto-generate a strong secret and warn
    JWT_SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "[SECURITY] JWT_SECRET_KEY is missing or uses the insecure default. "
        "A random key has been generated for THIS session. "
        "Set JWT_SECRET_KEY in your .env for persistence across restarts."
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ADMIN_INVITE_EXPIRY_HOURS = int(os.getenv("ADMIN_INVITE_EXPIRY_HOURS", "24"))

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "cui_campusbot_db")

# MongoDB Connection
mongo_client = None
mongo_db = None
mongo_gridfs = None

def connect_mongodb():
    """Connect to MongoDB Atlas"""
    global mongo_client, mongo_db, mongo_gridfs
    try:
        mongo_client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            tlsCAFile=certifi.where()
        )
        # Test connection
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[MONGODB_DB_NAME]
        mongo_gridfs = GridFS(mongo_db)
        print(f"[OK] Connected to MongoDB: {MONGODB_DB_NAME}")
        
        # Create indexes for documents collection
        mongo_db.documents.create_index('file_name')
        mongo_db.documents.create_index('uploaded_at')
        
        # Create indexes for feedback collection
        mongo_db.feedback.create_index('status')
        mongo_db.feedback.create_index('module')
        mongo_db.feedback.create_index('batch_section')
        mongo_db.feedback.create_index('created_at')
        mongo_db.feedback.create_index('rating')
        mongo_db.feedback.create_index('is_spam')

        # Create indexes for admin invites collection
        mongo_db.admin_invites.create_index('token', unique=True)
        mongo_db.admin_invites.create_index('token_hash', unique=True, sparse=True)
        mongo_db.admin_invites.create_index('email')
        mongo_db.admin_invites.create_index('expires_at')
        mongo_db.admin_invites.create_index('used')
        
        # Create default admin if not exists
        create_default_admin()
        # Keep app config in sync for blueprint access
        app.config['MONGO_DB'] = mongo_db
        return True
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {str(e)}")
        return False

def create_default_admin():
    """Create default admin user if not exists, or update role to super_admin."""
    global mongo_db
    if mongo_db is None:
        return
    
    admin_email = os.getenv("ADMIN_EMAIL", "fa22-bcs-099@cuivehari.edu.pk")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@CUI2024!")
    
    # Check if admin exists
    existing_admin = mongo_db.users.find_one({"email": admin_email})
    if existing_admin:
        # Ensure role is super_admin and recovery_email / department exist
        updates = {}
        if existing_admin.get("role") != "super_admin":
            updates["role"] = "super_admin"
        if not existing_admin.get("recovery_email"):
            updates["recovery_email"] = admin_email
        if not existing_admin.get("department"):
            updates["department"] = "CS"
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            mongo_db.users.update_one({"_id": existing_admin["_id"]}, {"$set": updates})
            print(f"[OK] Updated admin user fields: {list(updates.keys())}")
        else:
            print(f"[OK] Admin user already exists: {admin_email}")
        return
    
    # Create admin user with full schema
    password_hash = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    admin_doc = {
        "username": admin_email,
        "email": admin_email,
        "password_hash": password_hash,
        "role": "super_admin",
        "department": "CS",
        "recovery_email": admin_email,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    mongo_db.users.insert_one(admin_doc)
    print(f"[OK] Created default admin: {admin_email} (role=super_admin)")

# Initialize RAG Pipeline
print("Initializing RAG Pipeline...")
rag_pipeline = None
last_init_error = None

def has_pplx_key() -> bool:
    return bool(os.getenv("PPLX_API_KEY", "").strip())

def initialize_rag():
    """Initialize FREE RAG pipeline (no embedding quotas!)"""
    global rag_pipeline, last_init_error
    try:
        rag_pipeline = FreeRAGPipeline(
            data_directory=DATA_DIRECTORY,
            vector_store_collection="cui_campus_bot",
            vector_store_directory="chroma_db",
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            top_k=RETRIEVAL_TOP_K
        )
        
        # Check if data is already indexed in ChromaDB
        stats = rag_pipeline.vector_store.get_collection_stats()
        existing_count = stats.get('total_documents', 0)
        
        if existing_count > 0:
            # Embeddings already exist in ChromaDB — just set up the retriever, skip re-indexing
            print(f"[OK] ChromaDB already has {existing_count} documents — reusing saved embeddings (no re-indexing)")
            rag_pipeline.ensure_retriever()
        else:
            # First time: index data from MongoDB/local
            print("Indexing data for the first time...")
            rag_pipeline.index_data(force_reindex=False, mongo_db=mongo_db, mongo_gridfs=mongo_gridfs)
        
        print(f"[OK] RAG Pipeline ready! LLM Provider: {LLM_PROVIDER} (model: {PPLX_MODEL})")
        last_init_error = None
        return True
    except Exception as e:
        print(f"[ERROR] Error initializing RAG Pipeline: {str(e)}")
        last_init_error = str(e)
        return False

# Connect MongoDB first, then initialize RAG
connect_mongodb()

# Initialize Audit Logger with MongoDB reference
audit = get_audit_logger()
audit.set_db(mongo_db)

initialize_rag()


# ===========================================
# Security Headers (applied to every response)
# ===========================================

@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    # Content-Security-Policy — allow inline styles/scripts for existing templates
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self';"
    )
    return response


@app.errorhandler(429)
def rate_limit_handler(e):
    """Return JSON for Flask-Limiter 429 errors."""
    return jsonify({
        'detail': 'Too many requests. Please wait before trying again.',
        'retry_after': e.description,
    }), 429


# ===========================================
# Rate Limiting (login endpoint)
# ===========================================
# Simple in-memory rate limiter for login endpoint
from collections import defaultdict
import time as _time

_login_attempts = defaultdict(list)  # ip -> [timestamps]
LOGIN_RATE_LIMIT = 5          # max attempts
LOGIN_RATE_WINDOW = 300       # per 5-minute window (seconds)

def _check_login_rate_limit(ip: str) -> bool:
    """Return True if the IP is within rate limits, False if blocked."""
    now = _time.time()
    # Prune old entries
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOGIN_RATE_WINDOW]
    if len(_login_attempts[ip]) >= LOGIN_RATE_LIMIT:
        return False
    _login_attempts[ip].append(now)
    return True


# ===========================================
# JWT Authentication Functions
# ===========================================

def create_access_token(username: str, role: str = "admin", department: str = None) -> str:
    """Create a JWT access token with role and optional department claim."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    if department:
        to_encode["department"] = department
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify a JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'detail': 'Token is missing'}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({'detail': 'Token is invalid or expired'}), 401
        
        request.user = payload
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator to require admin or super_admin role"""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if request.user.get('role') not in ('admin', 'super_admin'):
            return jsonify({'detail': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """Decorator to require super_admin role."""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if request.user.get('role') != 'super_admin':
            return jsonify({'detail': 'Super admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    """
    Decorator to require one of the specified roles.
    Usage: @require_role('admin', 'super_admin', 'timetable_coordinator')
    """
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            user_role = request.user.get('role', '')
            if user_role not in allowed_roles:
                return jsonify({
                    'detail': f'Access denied. Required role(s): {", ".join(allowed_roles)}'
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_department_scope(*departments):
    """
    Decorator to restrict access to specific departments.
    The JWT must contain a 'department' claim matching one of the allowed values,
    OR the user must be an admin/super_admin (bypasses department check).
    Usage: @require_department_scope('CS', 'SE')
    """
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            user_role = request.user.get('role', '')
            # Admins bypass department scope
            if user_role in ('admin', 'super_admin'):
                return f(*args, **kwargs)
            user_dept = request.user.get('department', '')
            if user_dept not in departments:
                return jsonify({
                    'detail': f'Access restricted to department(s): {", ".join(departments)}'
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ===========================================
# Admin Unlock (Password-based Session)
# ===========================================
# Simple password unlock - no JWT required for students
# Admin enters password to unlock admin features

ADMIN_UNLOCK_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_SESSION_TIMEOUT_MINUTES = 30
SECURE_ADMIN_LOGIN_PATH = '/secure-admin-portal/login'
SECURE_ADMIN_DASHBOARD_PATH = '/secure-admin-portal/dashboard'
ADMIN_PORTAL_ROLES = ('admin', 'super_admin')


def _enforce_admin_dashboard_access():
    """Gate the hidden admin dashboard by login state and role."""
    if not session.get('is_logged_in'):
        return redirect(SECURE_ADMIN_LOGIN_PATH)

    user_role = session.get('user_role', 'user')
    if user_role not in ADMIN_PORTAL_ROLES:
        return '403 Forbidden', 403

    return None

def require_admin_unlocked(f):
    """
    Decorator to require admin access.
    Accepts EITHER:
    1. Session-based admin unlock (session['admin_unlocked'])
    2. JWT token with admin role (Authorization: Bearer <token>)
    Returns 403 if neither is valid.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        import time
        
        # Method 1: Check JWT token with admin role
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            payload = verify_token(token)
            if payload and payload.get('role') in ('admin', 'super_admin'):
                # Valid admin JWT token - allow access
                request.user = payload
                return f(*args, **kwargs)
        
        # Method 2: Check session-based admin unlock
        if session.get('admin_unlocked'):
            session_role = session.get('user_role')
            if session_role not in ADMIN_PORTAL_ROLES:
                session.pop('admin_unlocked', None)
                session.pop('admin_unlock_timestamp', None)
                print(f"[ACCESS DENIED] Admin session role mismatch for {request.path}")
                return jsonify({
                    'detail': 'Admin access required. Please log in with an admin account.',
                    'code': 'ADMIN_ROLE_REQUIRED'
                }), 403

            # Check session expiry
            unlock_timestamp = session.get('admin_unlock_timestamp')
            if unlock_timestamp:
                elapsed_seconds = time.time() - unlock_timestamp
                if elapsed_seconds > (ADMIN_SESSION_TIMEOUT_MINUTES * 60):
                    session.pop('admin_unlocked', None)
                    session.pop('admin_unlock_timestamp', None)
                    print(f"[ACCESS DENIED] Admin session expired for {request.path}")
                    return jsonify({
                        'detail': 'Admin session expired. Please unlock again.',
                        'code': 'ADMIN_SESSION_EXPIRED'
                    }), 403
            return f(*args, **kwargs)
        
        # Neither method succeeded
        print(f"[ACCESS DENIED] Admin unlock required for {request.path}")
        return jsonify({
            'detail': 'Admin access required. Please unlock admin panel first.',
            'code': 'ADMIN_UNLOCK_REQUIRED'
        }), 403
    return decorated


# ===========================================
# Helper Functions
# ===========================================

def _strip_markdown(text: str) -> str:
    """Remove common Markdown artifacts and citations for plain-text output.
    Preserves URLs so the frontend can make them clickable."""
    import re
    if not isinstance(text, str):
        return text
    # Convert markdown links [text](url) -> text (url)  — keeps the URL visible
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    # Remove headings starting with #
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers **, __, backticks
    text = text.replace("**", "").replace("__", "").replace("`", "")
    # Remove bracketed numeric citations like [1], [2], [1][2]
    text = re.sub(r"\[(?:\d+)(?:\s*[,;]\s*\d+)*\]", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim
    return text.strip()


@app.route('/')
def home():
    """Serve the main landing page"""
    return render_template('index.html')


@app.route('/chat')
@app.route('/chat.html')
def chat_page():
    """Serve the chat interface"""
    return render_template('chat.html')


@app.route('/timetable')
@app.route('/timetable.html')
def timetable_page():
    """Serve the timetable page"""
    return render_template('timetable.html')


@app.route('/student-portal')
@app.route('/student-portal.html')
def student_portal_page():
    """Serve the student portal page for timetable + notices."""
    return render_template('student_portal.html')


@app.route('/feedback')
@app.route('/feedback.html')
def feedback_page():
    """Serve the feedback page (new module-based form)"""
    return render_template('feedback_new.html')


@app.route(SECURE_ADMIN_LOGIN_PATH)
@app.route('/login')
@app.route('/login.html')
def login_page():
    """Serve the login page"""
    return render_template('login.html')


@app.route('/forgot-password')
def forgot_password_page():
    """Serve the forgot-password page"""
    return render_template('forgot_password.html')


@app.route('/reset-password')
def reset_password_page():
    """Serve the reset-password page (token arrives as ?token=...)"""
    return render_template('reset_password.html')


@app.route('/admin/register')
def admin_register_page():
    """Serve invite-based admin registration page (token arrives as ?token=...)."""
    return render_template('admin_register.html')


@app.route(SECURE_ADMIN_DASHBOARD_PATH)
@app.route('/secure-admin-portal')
def secure_admin_dashboard_page():
    """Serve the hidden admin dashboard page with backend role checks."""
    access_result = _enforce_admin_dashboard_access()
    if access_result:
        return access_result
    return render_template('admin.html')


@app.route('/admin/notifications')
@require_admin_unlocked
def admin_notifications_page():
    """Serve timetable/notification admin upload page."""
    return render_template('admin_notifications.html')


@app.route('/knowledge-base')
@app.route('/knowledge-base.html')
def knowledge_base_page():
    """Knowledge base UI is not exposed directly in navigation."""
    return redirect('/')


# ===========================================
# Authentication API Endpoints
# ===========================================

@app.route('/api/auth/token', methods=['POST'])
@limiter.limit("5 per minute")
def login_for_access_token():
    """
    OAuth2 Password Grant style login endpoint
    Accepts form data: username (email) and password
    Returns JWT access token
    Rate-limited: 5 attempts per minute per IP
    """
    # Rate limit check
    client_ip = request.remote_addr or "unknown"
    if not _check_login_rate_limit(client_ip):
        audit.login_failure("rate_limited", reason="Rate limit exceeded", ip_address=client_ip)
        return jsonify({
            'detail': 'Too many login attempts. Please wait before trying again.'
        }), 429

    # Check Content-Type and get credentials
    if request.content_type and 'application/x-www-form-urlencoded' in request.content_type:
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
    else:
        data = request.json or {}
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'detail': 'Email and password are required.'}), 400

    # Validate email format
    valid_email, email_err = validate_email(username)
    if not valid_email:
        return jsonify({'detail': 'Please enter a valid email address.'}), 400
    
    # Authenticate from MongoDB
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    
    if mongo_db is None:
        return jsonify({'detail': 'Database connection failed'}), 503
    
    # Find user by email
    user = mongo_db.users.find_one({"email": username})
    
    if not user:
        audit.login_failure(username, reason="User not found", ip_address=client_ip)
        return jsonify({'detail': 'Invalid email or password.'}), 401
    
    # Verify password (no trimming — raw input)
    try:
        password_bytes = password.encode('utf-8')
        hashed_bytes = user["password_hash"].encode('utf-8')
        if not bcrypt.checkpw(password_bytes, hashed_bytes):
            audit.login_failure(username, reason="Invalid password", ip_address=client_ip)
            return jsonify({'detail': 'Incorrect password. Please try again.'}), 401
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return jsonify({'detail': 'Authentication error'}), 500
    
    # Check if user is active
    if not user.get("is_active", True):
        audit.login_failure(username, reason="Account inactive", ip_address=client_ip)
        return jsonify({'detail': 'User account is inactive'}), 401
    
    # Create access token (include department if present)
    access_token = create_access_token(
        user["email"],
        role=user.get("role", "user"),
        department=user.get("department")
    )

    # Keep lightweight server-side login context for protected page routes.
    session['is_logged_in'] = True
    session['user_email'] = user["email"]
    session['user_role'] = user.get("role", "user")
    
    audit.login_success(user["email"], ip_address=client_ip)
    
    return jsonify({
        'access_token': access_token,
        'token_type': 'bearer',
        'expires_in': ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        'role': user.get("role", "user"),
        'user': {
            'id': str(user["_id"]),
            'username': user["email"],
            'email': user["email"],
            'role': user.get("role", "user")
        }
    })


@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current authenticated user info"""
    return jsonify({
        'username': request.user.get('sub'),
        'role': request.user.get('role'),
        'department': request.user.get('department'),
    })


@app.route('/api/auth/logout', methods=['POST'])
def logout_current_user():
    """Clear local authentication session state."""
    session.pop('is_logged_in', None)
    session.pop('user_email', None)
    session.pop('user_role', None)
    session.pop('admin_unlocked', None)
    session.pop('admin_unlock_timestamp', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})


# ===========================================
# Password Reset API Endpoints
# ===========================================

@app.route('/api/auth/forgot-password', methods=['POST'])
@limiter.limit("3 per 15 minutes")
def forgot_password():
    """
    Request a password reset email.
    POST JSON: { "email": "user@example.com" }
    Returns specific error messages as per the admin UX spec.
    """
    data = request.json or {}
    email = data.get('email', '').strip().lower()

    # Validate email format
    valid, err = validate_email(email)
    if not valid:
        return jsonify({'detail': 'Please enter a valid email address.'}), 400

    client_ip = request.remote_addr or "unknown"

    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database not available'}), 503

    audit.password_reset_request(email, ip_address=client_ip)

    # Check if user exists with admin role
    user = mongo_db.users.find_one({"email": email})
    if not user:
        return jsonify({'detail': 'No admin account found for this email.'}), 404

    user_role = user.get('role', 'user')
    if user_role not in ('admin', 'super_admin'):
        return jsonify({'detail': 'No admin account found for this email.'}), 404

    # Generate token
    success, raw_token, message, recovery_email = create_reset_token(
        mongo_db, email, requested_ip=client_ip
    )

    if not success or not raw_token:
        logger.error(f"[RESET] Token creation failed for {email}: {message}")
        return jsonify({'detail': 'Failed to generate reset link. Please try again.'}), 500

    # Send email to recovery_email (may differ from login email)
    send_to = recovery_email or email
    email_ok, email_msg = send_reset_email(
        recipient_email=send_to,
        reset_token=raw_token,
        expiry_minutes=RESET_TOKEN_EXPIRY_MINUTES,
    )
    if email_ok:
        audit.password_reset_email_sent(email, ip_address=client_ip)
    else:
        audit.password_reset_email_failed(email, reason=email_msg, ip_address=client_ip)
        logger.error(f"[RESET] Email delivery failed for {email}: {email_msg}")
        return jsonify({'detail': 'Failed to send reset email. Please try again later.'}), 500

    return jsonify({
        'success': True,
        'message': 'Password reset link sent successfully.'
    })


@app.route('/api/auth/validate-reset-token', methods=['GET'])
@limiter.limit("10 per 15 minutes")
def validate_token_endpoint():
    """
    Validate a password-reset token WITHOUT consuming it.
    GET /api/auth/validate-reset-token?token=<raw_token>
    Returns: { valid: bool, reason: str, message: str }
    """
    raw_token = request.args.get('token', '').strip()

    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({
            'valid': False,
            'reason': 'invalid_or_used',
            'message': 'Database not available.',
        }), 503

    result = validate_reset_token(mongo_db, raw_token)
    status_code = 200 if result['valid'] else 200  # always 200 — validity is in body
    return jsonify(result), status_code


@app.route('/api/auth/reset-password', methods=['POST'])
@limiter.limit("5 per 15 minutes")
def reset_password():
    """
    Reset password using a valid token.
    POST JSON: { "token": "...", "new_password": "...", "confirm_password": "..." }
    Email is resolved from the token record — not required in the request.
    Passwords are NOT trimmed before hashing.
    """
    data = request.json or {}
    token = data.get('token', '').strip()
    new_password = data.get('new_password', '')       # no .strip()
    confirm_password = data.get('confirm_password', '')  # no .strip()
    client_ip = request.remote_addr or "unknown"

    if not token:
        return jsonify({'detail': 'Reset token is required'}), 400

    if not new_password:
        return jsonify({'detail': 'New password is required'}), 400

    if new_password != confirm_password:
        return jsonify({'detail': 'Passwords do not match'}), 400

    valid, err = validate_password(new_password)
    if not valid:
        return jsonify({'detail': err}), 400

    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database not available'}), 503

    success, message, email = verify_and_reset_password(mongo_db, token, new_password)

    if success:
        audit.password_reset_complete(email, ip_address=client_ip)
        return jsonify({
            'success': True,
            'message': 'Password reset successful. Please log in again.'
        }), 200
    else:
        if email:
            audit.password_reset_failed(email, reason=message, ip_address=client_ip)
        else:
            audit.password_reset_invalid_token(ip_address=client_ip)
        return jsonify({'success': False, 'message': message}), 400


@app.route('/api/auth/users', methods=['GET'])
@super_admin_required
def list_users():
    """List all admin and super_admin users (super_admin only)."""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    
    if mongo_db is None:
        return jsonify([])
    
    try:
        users = list(
            mongo_db.users.find(
                {'role': {'$in': ['admin', 'super_admin']}},
                {'password_hash': 0},
            ).sort('created_at', -1)
        )
        result = []
        for user in users:
            result.append({
                'id': str(user.get('_id')),
                'username': user.get('username', user.get('email', '')),
                'email': user.get('email', ''),
                'role': user.get('role', 'user'),
                'is_active': user.get('is_active', True),
                'created_at': user.get('created_at', datetime.now(timezone.utc)).isoformat() if user.get('created_at') else None
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'detail': str(e)}), 500


@app.route('/admin/invite', methods=['POST'])
@super_admin_required
@limiter.limit('10 per hour')
def invite_admin_user():
    """Invite a new admin via email (super_admin only)."""
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()

    valid_email, email_error = validate_email(email)
    if not valid_email:
        return jsonify({'detail': email_error or 'Invalid email address'}), 400

    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database connection failed'}), 503

    # Prevent duplicate admin onboarding for existing account.
    existing_user = mongo_db.users.find_one({'email': email})
    if existing_user:
        return jsonify({'detail': 'An account with this email already exists'}), 400

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(hours=ADMIN_INVITE_EXPIRY_HOURS)
    invite_token = secrets.token_urlsafe(32)
    invite_token_hash = _hash_invite_token(invite_token)

    # Revoke any still-active invite for this email before issuing a new one.
    mongo_db.admin_invites.update_many(
        {
            'email': email,
            'used': False,
            'expires_at': {'$gt': issued_at},
        },
        {
            '$set': {
                'used': True,
                'used_at': issued_at,
                'revoked': True,
                'revoked_by': request.user.get('sub'),
            }
        },
    )

    creator_doc = mongo_db.users.find_one({'email': request.user.get('sub')}, {'_id': 1})
    created_by = str(creator_doc['_id']) if creator_doc else request.user.get('sub')

    invite_doc = {
        'email': email,
        'token_hash': invite_token_hash,
        'role': 'admin',
        'created_by': created_by,
        'created_at': issued_at,
        'expires_at': expires_at,
        'used': False,
        'used_at': None,
    }

    try:
        mongo_db.admin_invites.insert_one(invite_doc)
    except Exception as exc:
        logger.error(f'Failed to create admin invite for {email}: {exc}')
        return jsonify({'detail': 'Failed to create invitation'}), 500

    email_ok, email_message = send_admin_invite_email(
        recipient_email=email,
        invite_token=invite_token,
        expiry_hours=ADMIN_INVITE_EXPIRY_HOURS,
    )
    if not email_ok:
        logger.error(f'Failed to send invite email to {email}: {email_message}')
        return jsonify({'detail': 'Invitation created but email delivery failed'}), 500

    return jsonify({
        'success': True,
        'message': 'Admin invitation sent successfully',
        'email': email,
        'expires_at': expires_at.isoformat(),
    }), 201


@app.route('/admin/register', methods=['POST'])
@limiter.limit('20 per hour')
def register_admin_from_invite():
    """Create an admin account using a single-use invitation token."""
    data = request.json or {}
    invite_token = str(data.get('token', '')).strip()
    username = str(data.get('username', '')).strip()
    password = data.get('password', '')

    if not invite_token:
        return jsonify({'detail': 'Invitation token is required'}), 400
    if not username:
        return jsonify({'detail': 'Username is required'}), 400
    if len(username) < 3 or len(username) > 50:
        return jsonify({'detail': 'Username must be between 3 and 50 characters'}), 400

    valid_password, password_error = validate_password(password)
    if not valid_password:
        return jsonify({'detail': password_error or 'Invalid password'}), 400

    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database connection failed'}), 503

    invite_token_hash = _hash_invite_token(invite_token)
    invite = mongo_db.admin_invites.find_one({'token_hash': invite_token_hash})
    if not invite:
        # Legacy fallback for pre-hash invites.
        invite = mongo_db.admin_invites.find_one({'token': invite_token})
    if not invite:
        return jsonify({'detail': 'Invalid token'}), 400
    if invite.get('used', False):
        return jsonify({'detail': 'Used token'}), 400

    expires_at = invite.get('expires_at')
    now_utc = datetime.now(timezone.utc)
    if not isinstance(expires_at, datetime):
        return jsonify({'detail': 'Expired token'}), 400

    if expires_at.tzinfo is None:
        is_expired = expires_at <= datetime.utcnow()
    else:
        is_expired = expires_at <= now_utc

    if is_expired:
        return jsonify({'detail': 'Expired token'}), 400

    invite_email = str(invite.get('email', '')).strip().lower()
    existing_user = mongo_db.users.find_one({
        '$or': [
            {'email': invite_email},
            {'username': username},
        ]
    })
    if existing_user:
        return jsonify({'detail': 'Username or email already exists'}), 400

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = {
        'username': username,
        'email': invite_email,
        'password_hash': password_hash,
        'role': 'admin',
        'is_active': True,
        'created_at': now_utc,
        'updated_at': now_utc,
    }

    try:
        inserted = mongo_db.users.insert_one(new_user)
        mongo_db.admin_invites.update_one(
            {'_id': invite['_id']},
            {
                '$set': {
                    'used': True,
                    'used_at': now_utc,
                    'used_by': str(inserted.inserted_id),
                    'token_hash': invite_token_hash,
                }
            },
        )
    except Exception as exc:
        logger.error(f'Failed to register admin from invite: {exc}')
        return jsonify({'detail': 'Failed to register admin'}), 500

    return jsonify({
        'success': True,
        'message': 'Admin registration successful',
        'email': invite_email,
    }), 201


@app.route('/admin/users', methods=['GET'])
@super_admin_required
def list_admin_users():
    """List all admin users for super_admin management view."""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()

    if mongo_db is None:
        return jsonify([])

    try:
        users = list(
            mongo_db.users.find(
                {'role': {'$in': ['admin', 'super_admin']}},
                {'password_hash': 0},
            ).sort('created_at', -1)
        )
    except Exception as exc:
        logger.error(f'Failed to load admin users: {exc}')
        return jsonify({'detail': 'Failed to load admin users'}), 500

    result = []
    for user in users:
        created_at = user.get('created_at')
        result.append({
            'id': str(user.get('_id')),
            'username': user.get('username', user.get('email', '')),
            'email': user.get('email', ''),
            'role': user.get('role', 'admin'),
            'created_at': created_at.isoformat() if created_at else None,
        })

    return jsonify(result)


@app.route('/admin/users/<user_id>', methods=['DELETE'])
@super_admin_required
def delete_admin_user(user_id):
    """Delete an admin user (super_admin only)."""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database connection failed'}), 503

    try:
        target_object_id = ObjectId(user_id)
    except Exception:
        return jsonify({'detail': 'Invalid user id'}), 400

    current_actor = mongo_db.users.find_one({'email': request.user.get('sub')}, {'_id': 1, 'role': 1})
    if not current_actor:
        return jsonify({'detail': 'Unauthorized'}), 403

    if current_actor['_id'] == target_object_id:
        return jsonify({'detail': 'Cannot delete your own account'}), 400

    target_user = mongo_db.users.find_one({'_id': target_object_id})
    if not target_user:
        return jsonify({'detail': 'User not found'}), 404

    if target_user.get('role') == 'super_admin':
        return jsonify({'detail': 'Cannot delete another super admin'}), 403

    if target_user.get('role') != 'admin':
        return jsonify({'detail': 'Only admin accounts can be deleted here'}), 400

    try:
        mongo_db.users.delete_one({'_id': target_object_id})
    except Exception as exc:
        logger.error(f'Failed to delete admin user {user_id}: {exc}')
        return jsonify({'detail': 'Failed to delete user'}), 500

    return jsonify({'success': True, 'message': 'Admin deleted successfully'})


# ===========================================
# Admin Unlock API Endpoints
# ===========================================

@app.route('/api/admin/unlock', methods=['POST'])
@admin_required
def admin_unlock():
    """
    Unlock admin panel with password.
    Sets session flag for admin access.
    """
    import time
    valid_unlock, unlock_error = validate_password(ADMIN_UNLOCK_PASSWORD)
    if not valid_unlock:
        logger.error("[ADMIN UNLOCK] ADMIN_PASSWORD fails security policy; unlock disabled")
        return jsonify({'detail': 'Admin unlock is not configured'}), 500

    data = request.json or {}
    password = data.get('password', '').strip()
    
    if not password:
        print("[ADMIN UNLOCK] Missing password")
        return jsonify({'detail': 'Password required'}), 400
    
    if password != ADMIN_UNLOCK_PASSWORD:
        audit.login_failure("admin_unlock", reason="Invalid unlock password",
                           ip_address=request.remote_addr)
        print(f"[ADMIN UNLOCK] Invalid password attempt")
        return jsonify({'detail': 'Invalid password'}), 401
    
    # Set session flag with timestamp
    session['admin_unlocked'] = True
    session['admin_unlock_timestamp'] = time.time()
    session.permanent = True  # Use permanent session
    
    audit.admin_unlock(ip=request.remote_addr)
    print(f"[ADMIN UNLOCK] Admin unlocked successfully")
    return jsonify({
        'success': True,
        'message': 'Admin panel unlocked',
        'expires_in_minutes': ADMIN_SESSION_TIMEOUT_MINUTES
    })


@app.route('/api/admin/status', methods=['GET'])
@admin_required
def admin_status():
    """Check admin unlock status"""
    import time
    is_unlocked = session.get('admin_unlocked', False)
    unlock_timestamp = session.get('admin_unlock_timestamp')
    
    remaining_minutes = None
    if is_unlocked and unlock_timestamp:
        elapsed_seconds = time.time() - unlock_timestamp
        remaining_minutes = max(0, (ADMIN_SESSION_TIMEOUT_MINUTES * 60 - elapsed_seconds) / 60)
        if remaining_minutes <= 0:
            # Session expired
            session.pop('admin_unlocked', None)
            session.pop('admin_unlock_timestamp', None)
            is_unlocked = False
            remaining_minutes = None
    
    return jsonify({
        'unlocked': is_unlocked,
        'remaining_minutes': round(remaining_minutes, 1) if remaining_minutes is not None and remaining_minutes > 0 else None
    })


@app.route('/api/admin/logout', methods=['POST'])
@admin_required
def admin_logout():
    """Lock admin panel (logout)"""
    session.pop('admin_unlocked', None)
    session.pop('admin_unlock_timestamp', None)
    audit.admin_lock(ip=request.remote_addr)
    print("[ADMIN] Admin panel locked")
    return jsonify({'success': True, 'message': 'Admin panel locked'})


# ===========================================
# Feedback API Endpoints (new module-based system)
# ===========================================
# The new feedback system is in api/feedback_api.py.
# We register its Blueprint and wire admin auth + rate limiting here.

from api.feedback_api import feedback_bp

# Store mongo_db reference in app config so the blueprint can access it
app.config['MONGO_DB'] = mongo_db

# Register the blueprint (routes: /api/feedback, /api/admin/feedback, etc.)
app.register_blueprint(feedback_bp)
app.register_blueprint(timetable_bp)
app.register_blueprint(notification_bp)

# Protect admin-only timetable and notification write endpoints
_admin_new_views = [
    'timetable_v2.upload_timetable',
    'timetable_v2.delete_timetable',
    'timetable_v2.activate_timetable',
    'notifications_v2.create_notification',
    'notifications_v2.delete_notification',
]
for _view_name in _admin_new_views:
    if _view_name in app.view_functions:
        app.view_functions[_view_name] = require_admin_unlocked(
            app.view_functions[_view_name]
        )

# Apply rate limiting to the public feedback submit endpoint
limiter.limit("3 per 10 minutes")(
    app.view_functions['feedback.submit_feedback']
)

# Apply admin auth decorators to admin feedback routes
_admin_fb_views = [
    'feedback.get_feedback_list',
    'feedback.get_feedback_detail',
    'feedback.update_feedback_status',
    'feedback.toggle_feedback_spam',
]
for _view_name in _admin_fb_views:
    app.view_functions[_view_name] = require_admin_unlocked(
        app.view_functions[_view_name]
    )

# Keep legacy endpoints for backward compatibility
@app.route('/api/feedback/submit', methods=['POST'])
@limiter.limit("3 per 10 minutes")
def legacy_submit_feedback():
    """Legacy feedback submit - redirect to new endpoint."""
    from api.feedback_api import submit_feedback as _new_submit
    return _new_submit()


@app.route('/api/feedback/all', methods=['GET'])
@admin_required
def list_feedback():
    """Legacy: List all feedback (admin only) - proxies to new API."""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'feedbacks': []})
    try:
        status_filter = request.args.get('status_filter')
        query = {}
        if status_filter:
            query['status'] = status_filter
        feedbacks = list(mongo_db.feedback.find(query).sort('created_at', -1))
        result = []
        for fb in feedbacks:
            result.append({
                'id': str(fb.get('_id')),
                'username': fb.get('username', fb.get('name', 'anonymous')),
                'email': fb.get('email', ''),
                'subject': fb.get('subject', fb.get('category', '')),
                'message': fb.get('message', ''),
                'feedback_type': fb.get('feedback_type', fb.get('module', 'general')),
                'rating': fb.get('rating'),
                'status': fb.get('status', 'new'),
                'admin_response': fb.get('admin_response', fb.get('admin_note', '')),
                'created_at': fb.get('created_at', datetime.now(timezone.utc)).isoformat() if fb.get('created_at') else None
            })
        return jsonify({'feedbacks': result})
    except Exception as e:
        return jsonify({'detail': str(e)}), 500


@app.route('/api/feedback/<feedback_id>/respond', methods=['PUT'])
@admin_required
def respond_feedback(feedback_id):
    """Legacy: Respond to feedback (admin only)"""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database not available'}), 503
    response_text = request.args.get('response_text', '')
    new_status = request.args.get('new_status', 'reviewed')
    try:
        result = mongo_db.feedback.update_one(
            {'_id': ObjectId(feedback_id)},
            {'$set': {
                'admin_response': response_text,
                'admin_note': response_text,
                'status': new_status,
                'responded_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }}
        )
        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'Response saved'})
        return jsonify({'detail': 'Feedback not found'}), 404
    except Exception as e:
        return jsonify({'detail': str(e)}), 500


@app.route('/api/feedback/<feedback_id>', methods=['DELETE'])
@admin_required
def delete_feedback(feedback_id):
    """Delete feedback (admin only)"""
    global mongo_db
    if mongo_db is None:
        connect_mongodb()
    if mongo_db is None:
        return jsonify({'detail': 'Database not available'}), 503
    try:
        result = mongo_db.feedback.delete_one({'_id': ObjectId(feedback_id)})
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Feedback deleted'})
        return jsonify({'detail': 'Feedback not found'}), 404
    except Exception as e:
        return jsonify({'detail': str(e)}), 500


# ===========================================
# Document Upload API (Admin only)
# ===========================================

@app.route('/api/documents/upload', methods=['POST'])
@admin_required
def upload_document():
    """
    Upload a document to MongoDB Atlas (GridFS)
    Documents are stored in cloud, local copy only for RAG processing
    """
    global mongo_db, mongo_gridfs
    
    if 'file' not in request.files:
        return jsonify({'detail': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'detail': 'No file selected'}), 400
    
    # Allowed extensions
    allowed_extensions = ALLOWED_DOCUMENT_EXTENSIONS
    file_ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    
    try:
        # Ensure MongoDB connection
        if mongo_db is None or mongo_gridfs is None:
            print("[INFO] Reconnecting to MongoDB...")
            connect_mongodb()
        
        # Verify MongoDB is connected
        if mongo_db is None:
            return jsonify({'detail': 'MongoDB connection failed. Please try again.'}), 503
        
        if mongo_gridfs is None:
            return jsonify({'detail': 'MongoDB GridFS not available. Please try again.'}), 503
        
        # Read file content
        file_content = file.read()
        uploaded_file_size = len(file_content)

        valid_file, file_error = validate_file_upload(
            file.filename,
            uploaded_file_size,
            allowed_extensions=allowed_extensions,
        )
        if not valid_file:
            return jsonify({'detail': file_error}), 400
        
        print(f"[INFO] Uploading file: {file.filename} ({uploaded_file_size} bytes)")
        
        # Get form data
        raw_title = request.form.get('title', file.filename.rsplit('.', 1)[0])
        raw_description = request.form.get('description', '')
        title = sanitize_string(raw_title, max_length=200)
        description = sanitize_string(raw_description, max_length=500)
        
        # Store file in GridFS (MongoDB Atlas cloud storage)
        print("[INFO] Storing file in MongoDB GridFS...")
        gridfs_id = mongo_gridfs.put(
            file_content,
            filename=file.filename,
            content_type=f'application/{file_ext}'
        )
        print(f"[OK] File stored in GridFS with ID: {gridfs_id}")

        # Source of truth for stored size is GridFS metadata length.
        stored_file_size = uploaded_file_size
        try:
            grid_file = mongo_gridfs.get(gridfs_id)
            stored_file_size = (
                _coerce_file_size_bytes(getattr(grid_file, 'length', uploaded_file_size))
                or uploaded_file_size
            )
        except Exception as size_error:
            logger.warning(f"[WARN] Could not read GridFS file length for {file.filename}: {size_error}")
        
        # Create document record in MongoDB
        doc_record = {
            'title': title,
            'description': description,
            'file_name': file.filename,
            'file_type': file_ext,
            'file_size': stored_file_size,
            'gridfs_id': gridfs_id,
            'file_id': str(gridfs_id),
            'status': 'processing',
            'chunk_count': 0,
            'uploaded_by': request.user.get('sub', 'admin'),
            'uploaded_at': datetime.now(timezone.utc),
            'processed_at': None
        }
        
        # Insert document record into MongoDB
        result = mongo_db.documents.insert_one(doc_record)
        doc_id = str(result.inserted_id)
        print(f"[OK] Document record created with ID: {doc_id}")
        
        # Re-index the data from MongoDB
        chunk_count = 0
        if rag_pipeline:
            try:
                rag_pipeline.index_data(force_reindex=True, mongo_db=mongo_db, mongo_gridfs=mongo_gridfs)
                # Get chunk count from vector store
                if rag_pipeline.vector_store:
                    stats = rag_pipeline.vector_store.get_collection_stats()
                    chunk_count = stats.get('total_documents', 0)
            except Exception as reindex_err:
                print(f"[WARN] Re-indexing encountered an error (document still saved): {reindex_err}")
                # Document is safely saved in MongoDB even if re-indexing fails
        
        # Update document status in MongoDB
        mongo_db.documents.update_one(
            {'_id': ObjectId(doc_id)},
            {'$set': {
                'status': 'processed',
                'chunk_count': chunk_count,
                'processed_at': datetime.now(timezone.utc)
            }}
        )
        
        print(f"[OK] Document uploaded successfully to MongoDB Atlas!")
        
        audit.document_upload(
            user=request.user.get('sub', 'admin'),
            filename=file.filename
        )
        
        return jsonify({
            'success': True,
            'id': doc_id,
            'gridfs_id': str(gridfs_id),
            'title': title,
            'filename': file.filename,
            'file_size': stored_file_size,
            'file_size_mb': _bytes_to_mb(stored_file_size),
            'message': 'File uploaded to MongoDB Atlas successfully!'
        })
    except Exception as e:
        print(f"[ERROR] Upload failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'detail': f'Upload failed: {str(e)}'}), 500


@app.route('/api/documents/<doc_id>', methods=['DELETE'])
@admin_required
def delete_document(doc_id):
    """Delete a document from MongoDB and filesystem"""
    global mongo_db, mongo_gridfs
    
    try:
        if mongo_db is None:
            connect_mongodb()
        
        # Find document in MongoDB
        doc = None
        if mongo_db is not None:
            try:
                doc = mongo_db.documents.find_one({'_id': ObjectId(doc_id)})
            except:
                pass
        
        if doc:
            # Delete from GridFS if exists
            gridfs_object_id = _resolve_gridfs_object_id(doc)
            if mongo_gridfs is not None and gridfs_object_id:
                try:
                    mongo_gridfs.delete(gridfs_object_id)
                    print(f"[OK] Deleted file from GridFS: {gridfs_object_id}")
                except Exception as e:
                    print(f"[WARN] Could not delete from GridFS: {e}")
            
            # Delete from MongoDB
            mongo_db.documents.delete_one({'_id': ObjectId(doc_id)})
            
            # Re-index after deletion (non-blocking on errors)
            if rag_pipeline:
                try:
                    rag_pipeline.index_data(force_reindex=True, mongo_db=mongo_db, mongo_gridfs=mongo_gridfs)
                except Exception as reindex_err:
                    print(f"[WARN] Re-indexing after delete encountered an error: {reindex_err}")
            
            audit.document_delete(
                user=request.user.get('sub', 'admin'),
                doc_id=doc_id
            )
            
            return jsonify({'success': True, 'message': 'Document deleted'})
        
        return jsonify({'detail': 'Document not found'}), 404
    except Exception as e:
        print(f"[ERROR] Delete failed: {str(e)}")
        return jsonify({'detail': str(e)}), 500


@app.route('/api/documents', methods=['GET'])
@app.route('/api/documents/', methods=['GET'])
@admin_required
def list_documents():
    """List all documents from MongoDB"""
    global mongo_db
    
    try:
        if mongo_db is None:
            connect_mongodb()
        
        documents = []
        
        # Get documents from MongoDB
        if mongo_db is not None:
            projection = {
                'title': 1,
                'description': 1,
                'file_name': 1,
                'file_type': 1,
                'status': 1,
                'chunk_count': 1,
                'file_size': 1,
                'uploaded_by': 1,
                'uploaded_at': 1,
                'processed_at': 1,
            }
            cursor = mongo_db.documents.find({}, projection).sort('uploaded_at', -1)
            for doc in cursor:
                file_size_bytes = _coerce_file_size_bytes(doc.get('file_size'))
                if file_size_bytes is None:
                    file_size_bytes = 0

                documents.append({
                    'id': str(doc['_id']),
                    'title': doc.get('title', doc.get('file_name', 'Untitled')),
                    'description': doc.get('description', ''),
                    'file_name': doc.get('file_name', ''),
                    'file_type': doc.get('file_type', ''),
                    'status': doc.get('status', 'unknown'),
                    'chunk_count': doc.get('chunk_count', 0),
                    'file_size': file_size_bytes,
                    'file_size_mb': _bytes_to_mb(file_size_bytes),
                    'size': file_size_bytes,
                    'uploaded_by': doc.get('uploaded_by', ''),
                    'upload_date': doc.get('uploaded_at').isoformat() if doc.get('uploaded_at') else None,
                    'uploaded_at': doc.get('uploaded_at').isoformat() if doc.get('uploaded_at') else None,
                    'processed_at': doc.get('processed_at').isoformat() if doc.get('processed_at') else None
                })
        
        # If no documents in MongoDB, check local filesystem and sync
        if not documents and os.path.exists(DATA_DIRECTORY):
            for filename in os.listdir(DATA_DIRECTORY):
                filepath = os.path.join(DATA_DIRECTORY, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                    
                    # Sync to MongoDB
                    if mongo_db is not None:
                        # Check if already exists
                        existing = mongo_db.documents.find_one({'file_name': filename})
                        if not existing:
                            with open(filepath, 'rb') as f:
                                file_content = f.read()
                            
                            gridfs_id = None
                            if mongo_gridfs is not None:
                                gridfs_id = mongo_gridfs.put(
                                    file_content,
                                    filename=filename,
                                    content_type=f'application/{file_ext}'
                                )
                            
                            doc_record = {
                                'title': filename.rsplit('.', 1)[0] if '.' in filename else filename,
                                'description': 'Synced from filesystem',
                                'file_name': filename,
                                'file_type': file_ext,
                                'file_size': stat.st_size,
                                'gridfs_id': gridfs_id,
                                'file_id': str(gridfs_id) if gridfs_id else None,
                                'status': 'processed',
                                'chunk_count': 0,
                                'uploaded_by': 'system',
                                'uploaded_at': datetime.fromtimestamp(stat.st_mtime),
                                'processed_at': datetime.now(timezone.utc)
                            }
                            result = mongo_db.documents.insert_one(doc_record)
                            doc_record['id'] = str(result.inserted_id)
                            documents.append({
                                'id': str(result.inserted_id),
                                'title': doc_record['title'],
                                'description': doc_record['description'],
                                'file_name': doc_record['file_name'],
                                'file_type': doc_record['file_type'],
                                'status': doc_record['status'],
                                'chunk_count': doc_record['chunk_count'],
                                'file_size': doc_record['file_size'],
                                'file_size_mb': _bytes_to_mb(doc_record['file_size']),
                                'size': doc_record['file_size'],
                                'uploaded_by': doc_record['uploaded_by'],
                                'upload_date': doc_record['uploaded_at'].isoformat(),
                                'uploaded_at': doc_record['uploaded_at'].isoformat(),
                                'processed_at': doc_record['processed_at'].isoformat()
                            })
        
        return jsonify({'documents': documents})
    except Exception as e:
        print(f"[ERROR] List documents failed: {str(e)}")
        return jsonify({'detail': str(e)}), 500


@app.route('/admin/storage', methods=['GET'])
@app.route('/admin/storage/summary', methods=['GET'])
@admin_required
def get_admin_storage():
    """Get Atlas + application storage summary for admin dashboard."""
    global mongo_db

    try:
        if mongo_db is None:
            connect_mongodb()

        if mongo_db is None:
            return jsonify({'detail': 'Database connection unavailable'}), 503

        # Application-level usage from persisted document metadata.
        file_total_bytes = 0
        cursor = mongo_db.documents.find({}, {'file_size': 1})
        for doc in cursor:
            file_size_bytes = _coerce_file_size_bytes(doc.get('file_size'))
            if file_size_bytes is None:
                continue
            file_total_bytes += file_size_bytes

        file_used_mb = _bytes_to_mb(file_total_bytes)

        # Atlas-level usage from dbStats (actual database footprint).
        atlas_stats_ok = True
        try:
            db_stats = mongo_db.command('dbStats')
            data_size_bytes = _coerce_file_size_bytes(db_stats.get('dataSize')) or 0
            storage_size_bytes = _coerce_file_size_bytes(db_stats.get('storageSize')) or 0
            index_size_bytes = _coerce_file_size_bytes(db_stats.get('indexSize')) or 0

            # Prefer storageSize and include indexes to better approximate Atlas usage.
            base_bytes = storage_size_bytes if storage_size_bytes > 0 else data_size_bytes
            atlas_used_bytes = base_bytes + index_size_bytes
        except Exception as stats_error:
            atlas_stats_ok = False
            logger.warning(f"[WARN] dbStats failed; falling back to file usage: {stats_error}")
            atlas_used_bytes = file_total_bytes

        atlas_used_mb = _bytes_to_mb(atlas_used_bytes)
        remaining_mb = round(max(ATLAS_STORAGE_LIMIT_MB - atlas_used_mb, 0), 2)
        used_percentage = round((atlas_used_mb / ATLAS_STORAGE_LIMIT_MB) * 100, 2)

        return jsonify({
            'atlas_used_mb': atlas_used_mb,
            'file_used_mb': file_used_mb,
            'total_limit_mb': ATLAS_STORAGE_LIMIT_MB,
            'remaining_mb': remaining_mb,
            'used_percentage': used_percentage,
            # Compatibility keys for existing clients.
            'used_storage_mb': atlas_used_mb,
            'remaining_storage_mb': remaining_mb,
            'atlas_stats_available': atlas_stats_ok,
        })
    except Exception as e:
        logger.error(f"[ERROR] Failed to calculate storage usage: {str(e)}")
        return jsonify({
            'atlas_used_mb': 0.0,
            'file_used_mb': 0.0,
            'total_limit_mb': ATLAS_STORAGE_LIMIT_MB,
            'remaining_mb': ATLAS_STORAGE_LIMIT_MB,
            'used_percentage': 0.0,
            'detail': f'Failed to calculate storage usage: {str(e)}',
            'atlas_stats_available': False,
        }), 500


def _resolve_gridfs_object_id(doc: dict):
    """Resolve GridFS ObjectId from mixed metadata fields used across versions."""
    raw_file_id = doc.get('gridfs_id') or doc.get('file_id') or doc.get('gridfs_file_id')
    if not raw_file_id:
        return None

    if isinstance(raw_file_id, ObjectId):
        return raw_file_id

    try:
        return ObjectId(str(raw_file_id))
    except Exception:
        return None


@app.route('/admin/documents/<document_id>/view', methods=['GET'])
@admin_required
def view_document(document_id):
    """
    Stream a document from MongoDB GridFS for admin viewing.
    """
    global mongo_db, mongo_gridfs

    try:
        doc_object_id = ObjectId(document_id)
    except Exception:
        return jsonify({'detail': 'Invalid document ID'}), 400

    try:
        if mongo_db is None or mongo_gridfs is None:
            connect_mongodb()

        if mongo_db is None or mongo_gridfs is None:
            return jsonify({'detail': 'Database connection unavailable'}), 503

        doc = mongo_db.documents.find_one({'_id': doc_object_id})
        if not doc:
            return jsonify({'detail': 'Document not found'}), 404

        gridfs_object_id = _resolve_gridfs_object_id(doc)
        if not gridfs_object_id:
            return jsonify({'detail': 'File reference missing for document'}), 500

        try:
            grid_out = mongo_gridfs.get(gridfs_object_id)
        except NoFile:
            return jsonify({'detail': 'File not found in GridFS'}), 500

        file_name = doc.get('file_name') or getattr(grid_out, 'filename', 'document')
        safe_file_name = _sanitize_content_disposition_filename(file_name)
        file_type = str(doc.get('file_type', '')).lower()
        file_size = int(getattr(grid_out, 'length', 0) or 0)

        if file_type == 'pdf':
            mimetype = 'application/pdf'
            disposition_type = 'inline'
        elif file_type == 'docx':
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            disposition_type = 'attachment'
        elif file_type == 'txt':
            mimetype = 'text/plain'
            disposition_type = 'inline'
        else:
            mimetype = getattr(grid_out, 'content_type', None) or 'application/octet-stream'
            disposition_type = 'attachment'

        common_headers = {
            'Content-Type': mimetype,
            'Content-Disposition': f'{disposition_type}; filename="{safe_file_name}"',
            'X-Content-Type-Options': 'nosniff',
            'Accept-Ranges': 'bytes',
        }

        range_header = request.headers.get('Range')
        if range_header:
            byte_range = _parse_single_byte_range(range_header, file_size)
            if byte_range is None:
                return Response(
                    status=416,
                    headers={'Content-Range': f'bytes */{file_size}'}
                )

            start, end = byte_range
            length = end - start + 1
            grid_out.seek(start)
            partial_data = grid_out.read(length)

            headers = {
                **common_headers,
                'Content-Length': str(len(partial_data)),
                'Content-Range': f'bytes {start}-{end}/{file_size}',
            }
            return Response(partial_data, status=206, headers=headers)

        def stream_full_file():
            grid_out.seek(0)
            while True:
                chunk = grid_out.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

        headers = {
            **common_headers,
            'Content-Length': str(file_size),
        }

        return Response(
            stream_full_file(),
            status=200,
            headers=headers,
            direct_passthrough=True,
        )
    except Exception as e:
        logger.error(f"[ERROR] Failed to view document {document_id}: {str(e)}")
        return jsonify({'detail': f'Failed to load document: {str(e)}'}), 500


# ===========================================
# Stats API Endpoint (Admin Dashboard)
# ===========================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics for admin dashboard"""
    try:
        global mongo_db
        if mongo_db is None:
            connect_mongodb()
        
        # Count users
        users_count = 0
        if mongo_db is not None:
            users_count = mongo_db.users.count_documents({})
        
        # Count documents from MongoDB
        docs_count = 0
        if mongo_db is not None:
            docs_count = mongo_db.documents.count_documents({})
        # Fallback to local filesystem
        if docs_count == 0 and os.path.exists(DATA_DIRECTORY):
            docs_count = len([f for f in os.listdir(DATA_DIRECTORY) if os.path.isfile(os.path.join(DATA_DIRECTORY, f))])
        
        # Get knowledge chunks from vector store
        chunks_count = 0
        if rag_pipeline and rag_pipeline.vector_store:
            stats = rag_pipeline.vector_store.get_collection_stats()
            chunks_count = stats.get('total_documents', 0)
        
        # Count feedback
        feedback_count = 0
        if mongo_db is not None:
            try:
                feedback_count = mongo_db.feedback.count_documents({})
            except:
                feedback_count = 0
        
        # Get MongoDB storage usage (Free tier = 512MB)
        storage_info = {
            'used_mb': 0,
            'total_mb': 512,
            'used_percent': 0,
            'remaining_mb': 512
        }
        if mongo_db is not None:
            try:
                db_stats = mongo_db.command('dbStats')
                storage_bytes = db_stats.get('storageSize', 0) + db_stats.get('indexSize', 0)
                storage_mb = round(storage_bytes / (1024 * 1024), 2)
                storage_info = {
                    'used_mb': storage_mb,
                    'total_mb': 512,
                    'used_percent': round((storage_mb / 512) * 100, 1),
                    'remaining_mb': round(512 - storage_mb, 2)
                }
            except Exception as e:
                print(f"[WARN] Could not get storage stats: {e}")
        
        return jsonify({
            'users': users_count,
            'documents': {
                'total': docs_count
            },
            'knowledge_base': {
                'total_chunks': chunks_count
            },
            'feedback': feedback_count,
            'storage': storage_info
        })
    except Exception as e:
        return jsonify({
            'users': 0,
            'documents': {'total': 0},
            'knowledge_base': {'total_chunks': 0},
            'feedback': 0,
            'storage': {'used_mb': 0, 'total_mb': 512, 'used_percent': 0, 'remaining_mb': 512},
            'error': str(e)
        })


@app.route('/api/storage/check', methods=['GET'])
def check_storage():
    """Check MongoDB Atlas storage and list files in GridFS"""
    global mongo_db, mongo_gridfs
    
    try:
        if mongo_db is None or mongo_gridfs is None:
            connect_mongodb()
        
        if mongo_gridfs is None:
            return jsonify({'error': 'GridFS not available'}), 503
        
        # List all files in GridFS
        gridfs_files = []
        for grid_file in mongo_gridfs.find():
            gridfs_files.append({
                'id': str(grid_file._id),
                'filename': grid_file.filename,
                'size': grid_file.length,
                'upload_date': grid_file.upload_date.isoformat() if grid_file.upload_date else None
            })
        
        # Get documents from collection
        documents = []
        if mongo_db is not None:
            for doc in mongo_db.documents.find():
                documents.append({
                    'id': str(doc['_id']),
                    'title': doc.get('title'),
                    'file_name': doc.get('file_name'),
                    'gridfs_id': str(doc.get('gridfs_id')) if doc.get('gridfs_id') else None,
                    'file_size': doc.get('file_size')
                })
        
        # Get storage stats
        db_stats = mongo_db.command('dbStats')
        storage_bytes = db_stats.get('storageSize', 0) + db_stats.get('indexSize', 0)
        
        return jsonify({
            'success': True,
            'gridfs_files_count': len(gridfs_files),
            'gridfs_files': gridfs_files,
            'documents_count': len(documents),
            'documents': documents,
            'storage_bytes': storage_bytes,
            'storage_mb': round(storage_bytes / (1024 * 1024), 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===========================================
# Real-time Atlas Storage Endpoint
# ===========================================

@app.route('/api/atlas-storage', methods=['GET'])
def get_atlas_storage():
    """
    Get real-time MongoDB Atlas storage usage
    M0 Free Tier limit: 512 MB (documents + indexes)
    Calculates: usedBytes = dataSize + indexSize
    """
    global mongo_db, mongo_client
    
    LIMIT_BYTES = 536870912  # 512 MB in bytes
    
    # Default response for errors
    default_response = {
        'limitBytes': LIMIT_BYTES,
        'usedBytes': 0,
        'leftBytes': LIMIT_BYTES,
        'usedMB': 0.0,
        'leftMB': 512.0,
        'percentUsed': 0.0,
        'status': 'unknown',
        'updatedAt': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        if mongo_client is None:
            connect_mongodb()
        
        if mongo_client is None:
            default_response['error'] = 'MongoDB not connected'
            return jsonify(default_response), 503
        
        total_used_bytes = 0
        databases_checked = []
        
        # Try to list all databases and sum storage
        try:
            admin_db = mongo_client.admin
            db_list = admin_db.command('listDatabases')
            
            for db_info in db_list.get('databases', []):
                db_name = db_info.get('name')
                # Skip system databases
                if db_name in ['admin', 'local', 'config']:
                    continue
                    
                try:
                    db = mongo_client[db_name]
                    stats = db.command('dbStats', scale=1)
                    data_size = stats.get('dataSize', 0)
                    index_size = stats.get('indexSize', 0)
                    total_used_bytes += data_size + index_size
                    databases_checked.append(db_name)
                except Exception as db_err:
                    print(f"[WARN] Could not get stats for {db_name}: {db_err}")
                    
        except Exception as list_err:
            # Fallback: use main database only if listDatabases fails
            print(f"[INFO] listDatabases not available, using main DB: {list_err}")
            if mongo_db is not None:
                try:
                    stats = mongo_db.command('dbStats', scale=1)
                    data_size = stats.get('dataSize', 0)
                    index_size = stats.get('indexSize', 0)
                    total_used_bytes = data_size + index_size
                    databases_checked.append('cui_campusbot_db')
                except Exception as db_err:
                    print(f"[ERROR] Could not get main DB stats: {db_err}")
        
        # Calculate values
        left_bytes = max(0, LIMIT_BYTES - total_used_bytes)
        used_mb = round(total_used_bytes / (1024 * 1024), 2)
        left_mb = round(left_bytes / (1024 * 1024), 2)
        percent_used = round((total_used_bytes / LIMIT_BYTES) * 100, 2)
        
        # Determine status
        if percent_used >= 90:
            status = 'critical'
        elif percent_used >= 75:
            status = 'warning'
        else:
            status = 'healthy'
        
        return jsonify({
            'limitBytes': LIMIT_BYTES,
            'usedBytes': total_used_bytes,
            'leftBytes': left_bytes,
            'usedMB': used_mb,
            'leftMB': left_mb,
            'percentUsed': percent_used,
            'status': status,
            'databasesChecked': databases_checked,
            'updatedAt': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        print(f"[ERROR] Atlas storage check failed: {str(e)}")
        default_response['error'] = str(e)
        return jsonify(default_response), 500


# ===========================================
# Chat API Endpoint
# ===========================================

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests with multilingual support"""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        preferred_language = data.get('preferred_language', 'en')  # Default to English
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        # Get conversation history from session
        if 'conversation_history' not in session:
            session['conversation_history'] = []
        
        conversation_history = session['conversation_history']
        
        # Ensure pipeline is ready
        global rag_pipeline
        if rag_pipeline is None:
            if not has_pplx_key():
                return jsonify({
                    'success': False,
                    'error': 'LLM not configured. Set $env:PPLX_API_KEY and reload.',
                    'action': 'Set environment variable and call /api/reload or restart server.'
                }), 503
            # Try lazy init if key is present
            if not initialize_rag():
                return jsonify({
                    'success': False,
                    'error': 'Failed to initialize RAG pipeline.',
                    'details': last_init_error
                }), 503

        # Get language-specific system prompt and instruction
        system_prompt = get_system_prompt(preferred_language)
        language_instruction = get_language_instruction(preferred_language)
        is_roman_mode = (preferred_language == "roman")
        
        # Query RAG pipeline with language enforcement
        result = rag_pipeline.query(
            question=user_message,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            show_context=False,
            return_context=False,
            language_instruction=language_instruction,
            is_roman_mode=is_roman_mode
        )
        
        # Update conversation history
        conversation_history.append({
            'question': user_message,
            'answer': _strip_markdown(result['answer'])
        })
        
        # Keep last 10 turns
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
        
        session['conversation_history'] = conversation_history
        
        # Prepare response
        response = {
            'success': True,
            'answer': _strip_markdown(result['answer']),
            'sources': result.get('sources', []),
            'categories': result.get('categories', []),
            'language': preferred_language,
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while processing your request',
            'details': str(e)
        }), 500


@app.route('/api/clear', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    try:
        session['conversation_history'] = []
        return jsonify({
            'success': True,
            'message': 'Conversation history cleared'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/status', methods=['GET'])
def status():
    """Get system status"""
    try:
        if rag_pipeline:
            pipeline_status = rag_pipeline.get_pipeline_status()
            return jsonify({
                'success': True,
                'status': 'online',
                'pipeline': pipeline_status
            })
        else:
            return jsonify({
                'success': False,
                'status': 'offline',
                'message': 'RAG Pipeline not initialized',
                'requires_api_key': True,
                'env_var': 'PPLX_API_KEY',
                'last_error': last_init_error
            }), 503
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/suggestions', methods=['GET'])
def suggestions():
    """Get suggested questions"""
    suggested_questions = [
        "What are the admission requirements?",
        "How many campuses does COMSATS have?",
        "What scholarships are available?",
        "When do classes start?",
        "What is the fee structure?",
        "How do I apply for admission?",
        "What programs are offered?",
        "What are the campus facilities?"
    ]
    
    return jsonify({
        'success': True,
        'suggestions': suggested_questions
    })


@app.route('/api/reload', methods=['POST'])
def reload_pipeline():
    """Re-initialize the RAG pipeline (e.g., after setting API key)"""
    # Reload .env to pick up new keys without restarting the server
    try:
        from dotenv import load_dotenv as _ld
        _ld(override=True)
    except Exception:
        pass
    if not has_pplx_key():
        return jsonify({
            'success': False,
            'error': 'PPLX_API_KEY is not set. Set it and retry.'
        }), 400
    ok = initialize_rag()
    return jsonify({
        'success': ok,
        'message': 'RAG Pipeline reloaded' if ok else 'Failed to reload',
        'error': None if ok else last_init_error
    }), (200 if ok else 500)


# ===========================================
# Timetable & Notifications API
# Handled by: routes/timetable_routes.py (timetable_bp)
#             routes/notification_routes.py (notification_bp)
# Both blueprints are registered above at app initialisation.
# ===========================================


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs(DATA_DIRECTORY, exist_ok=True)
    
    # MongoDB already connected during module load
    print("\n" + "="*60)
    print("CUI Campus Chatbot - Web Interface")
    print("="*60)
    if mongo_db is not None:
        print("[OK] MongoDB Atlas connected successfully!")
    else:
        print("[WARNING] MongoDB connection failed - login will not work")
    
    print(f"")
    print(f"Server starting at: http://localhost:5000")
    print(f"")
    print(f"Available Pages:")
    print(f"  Home:      http://localhost:5000/")
    print(f"  Chat:      http://localhost:5000/chat")
    print(f"  Login:     http://localhost:5000/login")
    print(f"  Admin:     http://localhost:5000{SECURE_ADMIN_LOGIN_PATH}")
    print(f"  Timetable: http://localhost:5000/timetable")
    print(f"  Feedback:  http://localhost:5000/feedback")
    print(f"")
    print("Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
