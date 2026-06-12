"""
CUI CampusBot - Pydantic Models
Request/Response schemas for API endpoints
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum


# ===========================================
# Enums
# ===========================================

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    SUPER_ADMIN = "super_admin"
    HOD_CS = "hod_cs"
    HOD_SE = "hod_se"
    TIMETABLE_COORDINATOR = "timetable_coordinator"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


# ===========================================
# User Models
# ===========================================

class UserCreate(BaseModel):
    """Schema for user registration"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.USER
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "student1",
                "email": "student@cui.edu.pk",
                "password": "securepassword123",
                "role": "user"
            }
        }


class UserLogin(BaseModel):
    """Schema for user login"""
    username: str
    password: str


class UserResponse(BaseModel):
    """Schema for user response (no password)"""
    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserInDB(BaseModel):
    """Schema for user stored in database"""
    username: str
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ===========================================
# Token Models
# ===========================================

class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenData(BaseModel):
    """Schema for decoded JWT payload"""
    sub: str  # user_id
    username: str
    role: UserRole
    exp: datetime


# ===========================================
# Document Models
# ===========================================

class DocumentCreate(BaseModel):
    """Schema for document metadata creation"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class DocumentResponse(BaseModel):
    """Schema for document response"""
    id: str
    title: str
    description: Optional[str]
    file_name: str
    file_type: str
    uploaded_by: str
    upload_date: datetime
    status: DocumentStatus
    file_size: Optional[int] = None
    file_size_mb: Optional[float] = None
    chunk_count: Optional[int] = None
    embedding_model: Optional[str] = None
    gridfs_file_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    """Schema for list of documents"""
    documents: List[DocumentResponse]
    total: int


class AdminDocumentListItem(BaseModel):
    """Schema for admin document list response"""
    file_name: str
    file_type: str
    uploaded_by: str
    upload_date: datetime
    status: DocumentStatus


# ===========================================
# Chat Models
# ===========================================

class ChatMessage(BaseModel):
    """Schema for chat message"""
    message: str = Field(..., min_length=1, max_length=2000)
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "What are the admission requirements?"
            }
        }


class ChatResponse(BaseModel):
    """Schema for chat response"""
    success: bool
    answer: str
    sources: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatHistory(BaseModel):
    """Schema for chat history entry"""
    user_id: str
    question: str
    answer: str
    sources: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ===========================================
# API Response Models
# ===========================================

class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    """Error response schema"""
    detail: str
    error_code: Optional[str] = None


# ===========================================
# Health Check Models
# ===========================================

class HealthCheck(BaseModel):
    """Health check response"""
    status: str
    app_name: str
    version: str
    database: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ===========================================
# Feedback Models
# ===========================================

class FeedbackType(str, Enum):
    GENERAL = "general"
    BUG = "bug"
    SUGGESTION = "suggestion"
    COMPLAINT = "complaint"


class FeedbackCreate(BaseModel):
    """Schema for creating feedback (anonymous allowed)"""
    feedback_type: FeedbackType = FeedbackType.GENERAL
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=10, max_length=2000)
    rating: Optional[int] = Field(None, ge=1, le=5)
    name: Optional[str] = Field(None, max_length=100)  # Optional name for anonymous users
    email: Optional[str] = Field(None, max_length=200)  # Optional email for anonymous users
    
    class Config:
        json_schema_extra = {
            "example": {
                "feedback_type": "suggestion",
                "subject": "Improve chatbot responses",
                "message": "The chatbot should provide more detailed information about scholarships.",
                "rating": 4,
                "name": "Student",
                "email": "student@example.com"
            }
        }


class FeedbackResponse(BaseModel):
    """Schema for feedback response"""
    id: str
    user_id: str
    username: str
    feedback_type: FeedbackType
    subject: str
    message: str
    rating: Optional[int] = None
    status: str = "pending"
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    admin_response: Optional[str] = None
    email: Optional[str] = None


class FeedbackList(BaseModel):
    """Schema for list of feedback"""
    feedbacks: List[FeedbackResponse]
    total: int
