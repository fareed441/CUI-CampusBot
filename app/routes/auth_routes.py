"""
CUI CampusBot - Authentication Routes
OAuth2 Password Grant endpoints for login, register, token
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
import logging

from app.models import (
    UserCreate, UserResponse, UserLogin, Token, 
    MessageResponse, UserRole
)
from app.auth import (
    create_user, authenticate_user, create_access_token,
    get_user_by_id, update_user_role, deactivate_user
)
from app.dependencies import (
    get_current_user, get_current_active_user, get_admin_user
)
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, DEBUG
from app.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ===========================================
# OAuth2 Token Endpoint
# ===========================================

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None,
):
    """
    OAuth2 Password Grant - Login endpoint
    
    Returns JWT access token on successful authentication
    """
    user = authenticate_user(form_data.username, form_data.password)
    
    if not user:
        logger.warning(f"Failed login attempt for: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(
        user_id=str(user["_id"]),
        username=user["username"],
        role=user["role"]
    )
    
    # Build user response
    user_response = UserResponse(
        id=str(user["_id"]),
        username=user["username"],
        email=user["email"],
        role=UserRole(user["role"]),
        is_active=user["is_active"],
        created_at=user["created_at"]
    )
    
    logger.info(f"[OK] User logged in: {user['username']}")
    
    token_payload = Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response
    )

    if response is not None:
        response.set_cookie(
            key="cui_access_token",
            value=access_token,
            httponly=True,
            secure=not DEBUG,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    return token_payload


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """Clear auth cookie for web sessions."""
    response.delete_cookie("cui_access_token")
    return MessageResponse(message="Logged out successfully")


# ===========================================
# User Registration
# ===========================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    """
    Public self-registration is disabled.
    Admin accounts must be created through super_admin invitation flow.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Contact super admin for an invitation."
    )


# ===========================================
# Current User Endpoints
# ===========================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_active_user)
):
    """
    Get current authenticated user's profile
    """
    return current_user


@router.put("/me/password", response_model=MessageResponse)
async def change_password(
    old_password: str,
    new_password: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Change current user's password
    """
    from app.auth import verify_password, hash_password
    from security.input_validation import validate_password
    
    # Verify old password
    if not verify_password(old_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    valid_password, password_error = validate_password(new_password)
    if not valid_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=password_error
        )
    
    # Update password
    db = get_database()
    db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"password_hash": hash_password(new_password)}}
    )
    
    logger.info(f"[OK] Password changed for user: {current_user['username']}")
    return MessageResponse(message="Password updated successfully")


# ===========================================
# Admin User Management
# ===========================================

@router.get("/users", response_model=list[UserResponse])
async def list_all_users(
    admin_user: dict = Depends(get_admin_user)
):
    """
    List all users (Admin only)
    """
    db = get_database()
    users = list(db.users.find())
    
    return [
        UserResponse(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
            role=UserRole(user["role"]),
            is_active=user["is_active"],
            created_at=user["created_at"]
        )
        for user in users
    ]


@router.put("/users/{user_id}/role", response_model=MessageResponse)
async def change_user_role(
    user_id: str,
    new_role: UserRole,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Change a user's role (Admin only)
    """
    target_user = get_user_by_id(user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent admin from demoting themselves
    if str(admin_user["_id"]) == user_id and new_role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself"
        )
    
    success = update_user_role(user_id, new_role)
    if success:
        return MessageResponse(message=f"User role updated to {new_role.value}")
    
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to update user role"
    )


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def deactivate_user_account(
    user_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Deactivate a user account (Admin only)
    """
    # Prevent admin from deactivating themselves
    if str(admin_user["_id"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    success = deactivate_user(user_id)
    if success:
        return MessageResponse(message="User account deactivated")
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )


# ===========================================
# Admin Registration (Admin only)
# ===========================================

@router.post("/register-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_admin_user(
    user_data: UserCreate,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Register a new admin user (Admin only)
    """
    user_data.role = UserRole.ADMIN
    
    user = create_user(user_data)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    
    logger.info(f"[OK] Admin user created: {user['username']} by {admin_user['username']}")
    
    return UserResponse(
        id=str(user["_id"]),
        username=user["username"],
        email=user["email"],
        role=UserRole(user["role"]),
        is_active=user["is_active"],
        created_at=user["created_at"]
    )
