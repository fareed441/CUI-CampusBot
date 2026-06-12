"""
CUI CampusBot - Dependencies Module
FastAPI dependencies for JWT validation and role-based access control
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import logging

from app.auth import decode_access_token, get_user_by_id
from app.models import TokenData, UserRole, UserResponse
from datetime import datetime

logger = logging.getLogger(__name__)

# OAuth2 scheme - expects token in Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# Optional OAuth2 scheme - does not require auth
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Validate JWT token and return current user
    
    Raises:
        HTTPException 401: If token is invalid or expired
        HTTPException 401: If user not found or inactive
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    token_data = decode_access_token(token)
    if token_data is None:
        logger.warning("Invalid or expired token")
        raise credentials_exception
    
    # Check if token is expired
    if token_data.exp < datetime.utcnow():
        logger.warning(f"Token expired for user: {token_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    user = get_user_by_id(token_data.sub)
    if user is None:
        logger.warning(f"User not found: {token_data.sub}")
        raise credentials_exception
    
    # Check if user is active
    if not user.get("is_active", True):
        logger.warning(f"Inactive user attempted access: {token_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )
    
    return user


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> UserResponse:
    """
    Get current active user as UserResponse model
    """
    return UserResponse(
        id=str(current_user["_id"]),
        username=current_user["username"],
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        is_active=current_user["is_active"],
        created_at=current_user["created_at"]
    )


async def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify current user is an admin
    
    Raises:
        HTTPException 403: If user is not an admin
    """
    if current_user.get("role") not in ("admin", "super_admin"):
        logger.warning(f"Non-admin user attempted admin action: {current_user.get('username')}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user


async def get_super_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Verify current user is a super_admin."""
    if current_user.get("role") != "super_admin":
        logger.warning(
            f"Non-super-admin user attempted super-admin action: {current_user.get('username')}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required"
        )

    return current_user


async def get_optional_user(token: Optional[str] = Depends(oauth2_scheme_optional)) -> Optional[dict]:
    """
    Optionally validate JWT token and return current user
    Returns None if no token provided or token is invalid
    Used for public endpoints that can optionally use auth
    """
    if token is None:
        return None
    
    try:
        # Decode token
        token_data = decode_access_token(token)
        if token_data is None:
            return None
        
        # Check if token is expired
        if token_data.exp < datetime.utcnow():
            return None
        
        # Get user from database
        user = get_user_by_id(token_data.sub)
        if user is None or not user.get("is_active", True):
            return None
        
        return user
    except Exception:
        return None


class RoleChecker:
    """
    Role-based access control dependency
    
    Usage:
        @app.get("/admin-only", dependencies=[Depends(RoleChecker(["admin"]))])
    """
    
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles
    
    async def __call__(self, current_user: dict = Depends(get_current_user)) -> bool:
        if current_user.get("role") not in self.allowed_roles:
            logger.warning(
                f"Access denied for user {current_user.get('username')} "
                f"(role: {current_user.get('role')}, required: {self.allowed_roles})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(self.allowed_roles)}"
            )
        return True


# Pre-configured role checkers
require_admin = RoleChecker(["admin", "super_admin"])
require_user_or_admin = RoleChecker(["admin", "super_admin", "user"])


