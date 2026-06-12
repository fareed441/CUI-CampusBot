"""
CUI CampusBot - Authentication Module
OAuth2 + JWT + bcrypt password hashing
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os
import bcrypt
from bson import ObjectId
import logging

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_database
from app.models import UserCreate, UserInDB, TokenData, UserRole
from security.input_validation import validate_password

logger = logging.getLogger(__name__)

# ===========================================
# Password Hashing (using bcrypt directly)
# ===========================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# ===========================================
# JWT Token Operations
# ===========================================

def create_access_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token
    
    Args:
        user_id: User's MongoDB ObjectId as string
        username: User's username
        role: User's role (admin/user)
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expire,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.info(f"[OK] Created access token for user: {username}")
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT token
    
    Args:
        token: JWT token string
    
    Returns:
        TokenData if valid, None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        role: str = payload.get("role")
        exp: datetime = datetime.fromtimestamp(payload.get("exp"))
        
        if user_id is None or username is None:
            logger.warning("Token missing required claims")
            return None
        
        return TokenData(
            sub=user_id,
            username=username,
            role=UserRole(role),
            exp=exp
        )
        
    except JWTError as e:
        logger.warning(f"JWT decode error: {str(e)}")
        return None


# ===========================================
# User Operations
# ===========================================

def create_user(user_data: UserCreate) -> Optional[dict]:
    """
    Create a new user in the database
    
    Args:
        user_data: UserCreate schema with user details
    
    Returns:
        Created user document or None if failed
    """
    db = get_database()
    
    # Check if username or email already exists
    existing_user = db.users.find_one({
        "$or": [
            {"username": user_data.username},
            {"email": user_data.email}
        ]
    })
    
    if existing_user:
        logger.warning(f"User already exists: {user_data.username}")
        return None
    
    # Create user document
    user_doc = {
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "role": user_data.role.value,
        "is_active": True,
        "created_at": datetime.utcnow()
    }
    
    result = db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    
    logger.info(f"[OK] Created user: {user_data.username} (role: {user_data.role.value})")
    return user_doc


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user by username and password
    
    Args:
        username: User's username
        password: Plain text password
    
    Returns:
        User document if authenticated, None otherwise
    """
    db = get_database()
    
    # Find user by username
    user = db.users.find_one({"username": username})
    
    if not user:
        logger.warning(f"Authentication failed: User not found - {username}")
        return None
    
    if not user.get("is_active", True):
        logger.warning(f"Authentication failed: User inactive - {username}")
        return None
    
    if not verify_password(password, user["password_hash"]):
        logger.warning(f"Authentication failed: Invalid password - {username}")
        return None
    
    logger.info(f"[OK] User authenticated: {username}")
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    """
    Get user by MongoDB ObjectId
    
    Args:
        user_id: User's ObjectId as string
    
    Returns:
        User document or None
    """
    db = get_database()
    
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        return user
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {str(e)}")
        return None


def get_user_by_username(username: str) -> Optional[dict]:
    """
    Get user by username
    
    Args:
        username: User's username
    
    Returns:
        User document or None
    """
    db = get_database()
    return db.users.find_one({"username": username})


def update_user_role(user_id: str, new_role: UserRole) -> bool:
    """
    Update a user's role (admin only operation)
    
    Args:
        user_id: User's ObjectId as string
        new_role: New role to assign
    
    Returns:
        True if successful
    """
    db = get_database()
    
    result = db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role.value}}
    )
    
    if result.modified_count > 0:
        logger.info(f"[OK] Updated user {user_id} role to {new_role.value}")
        return True
    return False


def deactivate_user(user_id: str) -> bool:
    """
    Deactivate a user account
    
    Args:
        user_id: User's ObjectId as string
    
    Returns:
        True if successful
    """
    db = get_database()
    
    result = db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_active": False}}
    )
    
    if result.modified_count > 0:
        logger.info(f"[OK] Deactivated user: {user_id}")
        return True
    return False


# ===========================================
# Admin User Setup
# ===========================================

def create_default_admin():
    """
    Create default admin user if none exists
    Call this on application startup
    """
    db = get_database()
    
    # Check if any admin exists
    admin_exists = db.users.find_one({"role": {"$in": ["admin", "super_admin"]}})

    if admin_exists:
        logger.info("[OK] Admin user already exists")
        return

    default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@cui.edu.pk")
    default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "")

    valid_password, password_error = validate_password(default_password) if default_password else (False, "Password required")
    if not valid_password:
        logger.warning(
            "[WARN] Default admin not created: DEFAULT_ADMIN_PASSWORD is missing or weak"
        )
        return

    admin_data = UserCreate(
        username=default_username,
        email=default_email,
        password=default_password,
        role=UserRole.ADMIN
    )
    create_user(admin_data)
    logger.info("[OK] Created default admin user from environment config")
