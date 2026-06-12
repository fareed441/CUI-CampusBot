"""
CUI CampusBot - Document Routes
Admin-only document upload and management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import logging
import io
import secrets
import hashlib
import os
from urllib.parse import quote
from pydantic import BaseModel, EmailStr, Field

from app.models import (
    DocumentResponse, DocumentList, DocumentStatus, MessageResponse, AdminDocumentListItem
)
from app.dependencies import get_admin_user, get_current_user, get_optional_user, get_super_admin_user
from app.database import get_database
from app.auth import hash_password
from app.config import ALLOWED_FILE_TYPES, MAX_FILE_SIZE_MB
from security.email_service import send_admin_invite_email
from security.input_validation import validate_file_upload, sanitize_string, validate_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])
admin_router = APIRouter(prefix="/admin", tags=["Admin Documents"])

BYTES_IN_MB = 1024 * 1024
ATLAS_STORAGE_LIMIT_MB = 512.0
ADMIN_INVITE_EXPIRY_HOURS = int(os.getenv("ADMIN_INVITE_EXPIRY_HOURS", "24"))


class AdminInviteRequest(BaseModel):
    email: EmailStr


class AdminRegisterRequest(BaseModel):
    token: str = Field(..., min_length=1)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


def _bytes_to_mb(byte_size: int) -> float:
    """Convert bytes to MB rounded to 2 decimal places."""
    return round((byte_size or 0) / BYTES_IN_MB, 2)


def _get_stored_file_id(document: dict) -> Optional[str]:
    """Return the GridFS file reference from metadata across old/new schemas."""
    return document.get("file_id") or document.get("gridfs_file_id")


def _build_file_response_headers(file_name: str, file_type: str) -> tuple[str, str]:
    """
    Determine content-type and content-disposition for browser behavior.
    - PDF: inline display
    - DOCX: attachment download
    - TXT: inline display
    """
    safe_name = quote(file_name)

    if file_type == "pdf":
        return (
            "application/pdf",
            f"inline; filename=\"{file_name}\"; filename*=UTF-8''{safe_name}",
        )

    if file_type == "docx":
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{safe_name}",
        )

    if file_type == "txt":
        return (
            "text/plain; charset=utf-8",
            f"inline; filename=\"{file_name}\"; filename*=UTF-8''{safe_name}",
        )

    return (
        "application/octet-stream",
        f"attachment; filename=\"{file_name}\"; filename*=UTF-8''{safe_name}",
    )


def _hash_invite_token(token: str) -> str:
    """Hash admin invite tokens before persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ===========================================
# Document Upload (Admin Only)
# ===========================================

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    admin_user: dict = Depends(get_admin_user)
):
    """
    Upload a document to the knowledge base (Admin only)
    
    - Stores file in GridFS
    - Creates document metadata in MongoDB
    - Triggers RAG ingestion pipeline
    """
    # Validate file name and extension early
    file_ext = file.filename.split(".")[-1].lower() if file.filename else ""
    allowed_extensions = frozenset([ext.lower() for ext in ALLOWED_FILE_TYPES])
    
    # Read file content
    file_content = await file.read()
    
    # Validate file size and extension
    uploaded_file_size = len(file_content)
    valid_file, file_error = validate_file_upload(
        file.filename,
        uploaded_file_size,
        allowed_extensions=allowed_extensions,
    )
    if not valid_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=file_error
        )

    file_size_mb = uploaded_file_size / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size ({file_size_mb:.2f} MB) exceeds maximum ({MAX_FILE_SIZE_MB} MB)"
        )
    
    db = get_database()
    
    # Store file in GridFS
    gridfs_file_id = db.store_file(
        file_data=file_content,
        filename=file.filename,
        content_type=file.content_type,
        metadata={
            "uploaded_by": str(admin_user["_id"]),
            "title": title
        }
    )

    stored_file_size = uploaded_file_size
    try:
        grid_out = db.gridfs.get(ObjectId(gridfs_file_id))
        stored_file_size = int(getattr(grid_out, "length", uploaded_file_size) or uploaded_file_size)
    except Exception as size_error:
        logger.warning(f"Could not read GridFS length for {file.filename}: {size_error}")
    
    # Create document metadata
    safe_title = sanitize_string(title, max_length=200)
    safe_description = sanitize_string(description or "", max_length=500)

    doc_metadata = {
        "title": safe_title,
        "description": safe_description or None,
        "file_name": file.filename,
        "file_type": file_ext,
        "file_size": stored_file_size,
        "file_size_mb": _bytes_to_mb(stored_file_size),
        "uploaded_by": str(admin_user["_id"]),
        "uploader_username": admin_user["username"],
        "upload_date": datetime.utcnow(),
        "status": DocumentStatus.UPLOADED.value,
        "file_id": gridfs_file_id,
        "gridfs_file_id": gridfs_file_id,
        "chunk_count": None,
        "embedding_model": None
    }
    
    result = db.documents.insert_one(doc_metadata)
    doc_id = str(result.inserted_id)
    
    logger.info(f"[OK] Document uploaded: {file.filename} by {admin_user['username']}")
    
    # Trigger RAG ingestion (async in background)
    try:
        from app.rag.ingestion import process_document
        process_document(doc_id, file_content, file_ext)
    except Exception as e:
        logger.error(f"RAG ingestion error: {str(e)}")
        # Update status to failed
        db.documents.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": DocumentStatus.FAILED.value}}
        )
    
    return DocumentResponse(
        id=doc_id,
        title=safe_title,
        description=safe_description or None,
        file_name=file.filename,
        file_type=file_ext,
        uploaded_by=admin_user["username"],
        upload_date=doc_metadata["upload_date"],
        status=DocumentStatus(doc_metadata["status"]),
        file_size=doc_metadata["file_size"],
        file_size_mb=doc_metadata["file_size_mb"],
        gridfs_file_id=gridfs_file_id
    )


# ===========================================
# Admin Document Listing (Admin Only)
# ===========================================

@admin_router.get("/documents", response_model=List[AdminDocumentListItem])
async def list_admin_documents(
    my_docs: Optional[bool] = False,
    admin_user: dict = Depends(get_admin_user)
):
    """
    List document metadata for admin visibility
    """
    db = get_database()

    query = {}
    if my_docs:
        query["uploaded_by"] = str(admin_user["_id"])

    projection = {
        "file_name": 1,
        "file_type": 1,
        "uploaded_by": 1,
        "upload_date": 1,
        "status": 1
    }

    try:
        documents = list(
            db.documents.find(query, projection).sort("upload_date", -1)
        )
    except Exception as e:
        logger.error(f"Admin document listing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch documents"
        )

    if not documents:
        return []

    return [
        AdminDocumentListItem(
            file_name=doc.get("file_name", ""),
            file_type=doc.get("file_type", ""),
            uploaded_by=str(doc.get("uploaded_by", "")),
            upload_date=doc.get("upload_date"),
            status=DocumentStatus(doc.get("status", DocumentStatus.UPLOADED.value))
        )
        for doc in documents
    ]


@admin_router.get("/storage")
@admin_router.get("/storage/summary")
async def get_admin_storage(
    admin_user: dict = Depends(get_admin_user)
):
    """Get Atlas + application storage summary for admin dashboard."""
    db = get_database()

    try:
        file_total_bytes = 0
        cursor = db.documents.find({}, {"file_size": 1})
        for doc in cursor:
            raw_file_size = doc.get("file_size")
            try:
                file_size_bytes = int(raw_file_size)
                if file_size_bytes < 0:
                    continue
                file_total_bytes += file_size_bytes
            except (TypeError, ValueError):
                continue

        file_used_mb = _bytes_to_mb(file_total_bytes)

        atlas_stats_available = True
        try:
            db_stats = db.db.command("dbStats")
            data_size_bytes = int(db_stats.get("dataSize") or 0)
            storage_size_bytes = int(db_stats.get("storageSize") or 0)
            index_size_bytes = int(db_stats.get("indexSize") or 0)
            base_bytes = storage_size_bytes if storage_size_bytes > 0 else data_size_bytes
            atlas_used_bytes = max(base_bytes + index_size_bytes, 0)
        except Exception as stats_error:
            atlas_stats_available = False
            logger.warning(f"dbStats failed; falling back to file usage: {stats_error}")
            atlas_used_bytes = file_total_bytes

        atlas_used_mb = _bytes_to_mb(atlas_used_bytes)
        remaining_mb = round(max(ATLAS_STORAGE_LIMIT_MB - atlas_used_mb, 0), 2)
        used_percentage = round((atlas_used_mb / ATLAS_STORAGE_LIMIT_MB) * 100, 2)

        return {
            "atlas_used_mb": atlas_used_mb,
            "file_used_mb": file_used_mb,
            "total_limit_mb": ATLAS_STORAGE_LIMIT_MB,
            "remaining_mb": remaining_mb,
            "used_percentage": used_percentage,
            # Compatibility keys for existing clients.
            "used_storage_mb": atlas_used_mb,
            "remaining_storage_mb": remaining_mb,
            "atlas_stats_available": atlas_stats_available,
        }
    except Exception as e:
        logger.error(f"Failed to calculate admin storage usage: {str(e)}")
        return {
            "atlas_used_mb": 0.0,
            "file_used_mb": 0.0,
            "total_limit_mb": ATLAS_STORAGE_LIMIT_MB,
            "remaining_mb": ATLAS_STORAGE_LIMIT_MB,
            "used_percentage": 0.0,
            "used_storage_mb": 0.0,
            "remaining_storage_mb": ATLAS_STORAGE_LIMIT_MB,
            "atlas_stats_available": False,
        }


@admin_router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_admin(
    invite: AdminInviteRequest,
    super_admin_user: dict = Depends(get_super_admin_user)
):
    """Invite a new admin via email (super_admin only)."""
    db = get_database()
    email = invite.email.strip().lower()

    existing_user = db.users.find_one({"email": email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists"
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ADMIN_INVITE_EXPIRY_HOURS)
    invite_token = secrets.token_urlsafe(32)
    invite_token_hash = _hash_invite_token(invite_token)

    db.db.admin_invites.update_many(
        {
            "email": email,
            "used": False,
            "expires_at": {"$gt": now},
        },
        {
            "$set": {
                "used": True,
                "used_at": now,
                "revoked": True,
                "revoked_by": str(super_admin_user["_id"]),
            }
        },
    )

    invite_doc = {
        "email": email,
        "token_hash": invite_token_hash,
        "role": "admin",
        "created_by": str(super_admin_user["_id"]),
        "created_at": now,
        "expires_at": expires_at,
        "used": False,
        "used_at": None,
    }

    try:
        db.db.admin_invites.insert_one(invite_doc)
    except Exception as e:
        logger.error(f"Failed to create invite for {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation"
        )

    email_ok, email_message = send_admin_invite_email(
        recipient_email=email,
        invite_token=invite_token,
        expiry_hours=ADMIN_INVITE_EXPIRY_HOURS,
    )
    if not email_ok:
        logger.error(f"Failed to send invite email to {email}: {email_message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invitation created but email delivery failed"
        )

    return {
        "success": True,
        "message": "Admin invitation sent successfully",
        "email": email,
        "expires_at": expires_at.isoformat(),
    }


@admin_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_admin(invite_registration: AdminRegisterRequest):
    """Register an admin account from a valid invite token."""
    db = get_database()
    now = datetime.now(timezone.utc)

    valid_password, password_error = validate_password(invite_registration.password)
    if not valid_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=password_error
        )

    invite_token_hash = _hash_invite_token(invite_registration.token)
    invite = db.db.admin_invites.find_one({"token_hash": invite_token_hash})
    if not invite:
        # Legacy fallback for pre-hash invites.
        invite = db.db.admin_invites.find_one({"token": invite_registration.token})
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token"
        )

    if invite.get("used", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Used token"
        )

    expires_at = invite.get("expires_at")
    if not isinstance(expires_at, datetime):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expired token"
        )

    if expires_at.tzinfo is None:
        is_expired = expires_at <= datetime.utcnow()
    else:
        is_expired = expires_at <= now

    if is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expired token"
        )

    invite_email = str(invite.get("email", "")).strip().lower()
    existing_user = db.users.find_one(
        {
            "$or": [
                {"email": invite_email},
                {"username": invite_registration.username},
            ]
        }
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )

    new_user = {
        "username": invite_registration.username,
        "email": invite_email,
        "password_hash": hash_password(invite_registration.password),
        "role": "admin",
        "is_active": True,
        "created_at": now,
    }

    try:
        inserted = db.users.insert_one(new_user)
        db.db.admin_invites.update_one(
            {"_id": invite["_id"]},
            {
                "$set": {
                    "used": True,
                    "used_at": now,
                    "used_by": str(inserted.inserted_id),
                    "token_hash": invite_token_hash,
                }
            },
        )
    except Exception as e:
        logger.error(f"Failed to register admin via invite: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register admin"
        )

    return {
        "success": True,
        "message": "Admin registration successful",
        "email": invite_email,
    }


@admin_router.get("/users")
async def list_admin_users(
    super_admin_user: dict = Depends(get_super_admin_user)
):
    """List all admin and super_admin accounts for super admin control panel."""
    db = get_database()

    users = list(
        db.users.find(
            {"role": {"$in": ["admin", "super_admin"]}},
            {"password_hash": 0},
        ).sort("created_at", -1)
    )

    results = []
    for user in users:
        created_at = user.get("created_at")
        results.append(
            {
                "id": str(user.get("_id")),
                "username": user.get("username", user.get("email", "")),
                "email": user.get("email", ""),
                "role": user.get("role", "admin"),
                "created_at": created_at.isoformat() if created_at else None,
            }
        )

    return results


@admin_router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: str,
    super_admin_user: dict = Depends(get_super_admin_user)
):
    """Delete an admin account (super_admin only)."""
    db = get_database()

    try:
        target_object_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id"
        )

    if str(super_admin_user["_id"]) == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    target_user = db.users.find_one({"_id": target_object_id})
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if target_user.get("role") == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete another super admin"
        )

    if target_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only admin accounts can be deleted here"
        )

    db.users.delete_one({"_id": target_object_id})
    return {"success": True, "message": "Admin deleted successfully"}


@admin_router.get("/documents/{document_id}/view")
async def view_document(
    document_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Stream a document from GridFS for admin viewing.
    """
    db = get_database()

    try:
        object_id = ObjectId(document_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID"
        )

    try:
        doc = db.documents.find_one({"_id": object_id})
    except Exception as e:
        logger.error(f"Database error while loading document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while fetching document"
        )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    file_id = _get_stored_file_id(doc)
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file reference is missing"
        )

    file_data = db.get_file(file_id)
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in GridFS"
        )

    file_name = doc.get("file_name", "document")
    file_type = str(doc.get("file_type", "")).lower()
    media_type, content_disposition = _build_file_response_headers(file_name, file_type)

    logger.info(
        f"[OK] Admin viewed document: {file_name} (doc_id={document_id}, admin={admin_user.get('username')})"
    )

    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition}
    )


# ===========================================
# Document Listing (Public - no login required)
# ===========================================

@router.get("/", response_model=DocumentList)
async def list_documents(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    List all documents in the knowledge base (Public endpoint)
    
    - Admins see all documents (any status)
    - Public/Users see only processed documents
    """
    db = get_database()
    
    # Build query
    query = {}
    is_admin = current_user and current_user.get("role") in ("admin", "super_admin")
    
    if status_filter and is_admin:
        # Only admins can filter by status
        query["status"] = status_filter
    elif not is_admin:
        # Non-admins and public only see processed documents
        query["status"] = DocumentStatus.PROCESSED.value
    
    # Get documents
    documents = list(
        db.documents.find(query)
        .sort("upload_date", -1)
        .skip(skip)
        .limit(limit)
    )
    
    total = db.documents.count_documents(query)
    
    doc_responses = [
        DocumentResponse(
            id=str(doc["_id"]),
            title=doc["title"],
            description=doc.get("description"),
            file_name=doc["file_name"],
            file_type=doc["file_type"],
            uploaded_by=doc.get("uploader_username", "unknown"),
            upload_date=doc["upload_date"],
            status=DocumentStatus(doc["status"]),
            file_size=(
                int(doc.get("file_size"))
                if doc.get("file_size") is not None and str(doc.get("file_size")).isdigit()
                else None
            ),
            file_size_mb=(
                doc.get("file_size_mb")
                if doc.get("file_size_mb") is not None
                else _bytes_to_mb(int(doc.get("file_size") or 0))
            ),
            chunk_count=doc.get("chunk_count"),
            embedding_model=doc.get("embedding_model"),
            gridfs_file_id=doc.get("gridfs_file_id")
        )
        for doc in documents
    ]
    
    return DocumentList(documents=doc_responses, total=total)


# ===========================================
# Single Document Operations
# ===========================================

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get document metadata by ID
    """
    db = get_database()
    
    try:
        doc = db.documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID"
        )
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if current_user.get("role") not in ("admin", "super_admin"):
        if doc.get("status") != DocumentStatus.PROCESSED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access restricted to processed documents"
            )

    return DocumentResponse(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc.get("description"),
        file_name=doc["file_name"],
        file_type=doc["file_type"],
        uploaded_by=doc.get("uploader_username", "unknown"),
        upload_date=doc["upload_date"],
        status=DocumentStatus(doc["status"]),
        file_size=(
            int(doc.get("file_size"))
            if doc.get("file_size") is not None and str(doc.get("file_size")).isdigit()
            else None
        ),
        file_size_mb=doc.get("file_size_mb"),
        chunk_count=doc.get("chunk_count"),
        embedding_model=doc.get("embedding_model"),
        gridfs_file_id=doc.get("gridfs_file_id")
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Download original document file (Admin only)
    """
    db = get_database()
    
    try:
        doc = db.documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID"
        )
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_id = _get_stored_file_id(doc)
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file reference is missing"
        )

    # Get file from GridFS
    file_data = db.get_file(file_id)
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage"
        )
    
    # Return file stream
    media_type, content_disposition = _build_file_response_headers(
        doc.get("file_name", "document"),
        str(doc.get("file_type", "")).lower()
    )

    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition}
    )


@router.delete("/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Delete a document and its embeddings (Admin only)
    """
    db = get_database()
    
    try:
        doc = db.documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID"
        )
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_id = _get_stored_file_id(doc)

    # Delete from GridFS
    if file_id:
        db.delete_file(file_id)
    
    # Delete from ChromaDB
    try:
        from app.rag.ingestion import delete_document_embeddings
        delete_document_embeddings(document_id)
    except Exception as e:
        logger.warning(f"Failed to delete embeddings: {str(e)}")
    
    # Delete metadata
    db.documents.delete_one({"_id": ObjectId(document_id)})
    
    logger.info(f"[OK] Document deleted: {doc['file_name']} by {admin_user['username']}")
    
    return MessageResponse(message="Document deleted successfully")


# ===========================================
# Reprocess Document (Admin Only)
# ===========================================

@router.post("/{document_id}/reprocess", response_model=MessageResponse)
async def reprocess_document(
    document_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """
    Reprocess a document through the RAG pipeline (Admin only)
    """
    db = get_database()
    
    try:
        doc = db.documents.find_one({"_id": ObjectId(document_id)})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document ID"
        )
    
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_id = _get_stored_file_id(doc)
    if not file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file reference is missing"
        )

    # Get file from GridFS
    file_data = db.get_file(file_id)
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found in storage"
        )
    
    # Update status
    db.documents.update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"status": DocumentStatus.PROCESSING.value}}
    )
    
    # Trigger reprocessing
    try:
        from app.rag.ingestion import process_document
        process_document(document_id, file_data, doc["file_type"])
        return MessageResponse(message="Document reprocessing started")
    except Exception as e:
        logger.error(f"Reprocessing error: {str(e)}")
        db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": DocumentStatus.FAILED.value}}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reprocessing failed: {str(e)}"
        )
