"""
CUI CampusBot - Feedback Routes
Handles user feedback submission (anonymous allowed) and admin review
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
import logging

from app.dependencies import get_current_user, require_admin
from app.database import get_database
from app.models import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackList,
    FeedbackType,
    MessageResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


# ===========================================
# Public Endpoints (No login required)
# ===========================================

@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackCreate,
    request: Request
):
    """
    Submit feedback (PUBLIC - No login required)
    Students can submit feedback anonymously
    """
    db = get_database()
    
    # Use provided name/email or default to anonymous
    username = feedback.name if feedback.name else "Anonymous Student"
    
    feedback_doc = {
        "user_id": "anonymous",
        "username": username,
        "email": feedback.email,
        "feedback_type": feedback.feedback_type.value,
        "subject": feedback.subject,
        "message": feedback.message,
        "rating": feedback.rating,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "reviewed_at": None,
        "admin_response": None,
        "ip_address": request.client.host if request.client else "unknown"
    }
    
    result = db.feedback.insert_one(feedback_doc)
    
    logger.info(f"Feedback submitted by {username}: {feedback.subject}")
    
    return FeedbackResponse(
        id=str(result.inserted_id),
        user_id="anonymous",
        username=username,
        feedback_type=feedback.feedback_type,
        subject=feedback.subject,
        message=feedback.message,
        rating=feedback.rating,
        status="pending",
        created_at=feedback_doc["created_at"],
        email=feedback.email
    )


@router.get("/my", response_model=FeedbackList)
async def get_my_feedback(
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user's feedback submissions
    """
    db = get_database()
    
    feedbacks = list(db.feedback.find(
        {"user_id": ObjectId(current_user["id"])}
    ).sort("created_at", -1))
    
    feedback_list = []
    for fb in feedbacks:
        feedback_list.append(FeedbackResponse(
            id=str(fb["_id"]),
            user_id=str(fb["user_id"]),
            username=fb["username"],
            feedback_type=fb["feedback_type"],
            subject=fb["subject"],
            message=fb["message"],
            rating=fb.get("rating"),
            status=fb.get("status", "pending"),
            created_at=fb["created_at"],
            reviewed_at=fb.get("reviewed_at"),
            admin_response=fb.get("admin_response")
        ))
    
    return FeedbackList(feedbacks=feedback_list, total=len(feedback_list))


# ===========================================
# Admin Endpoints
# ===========================================

@router.get("/all", response_model=FeedbackList)
async def get_all_feedback(
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, reviewed, resolved"),
    admin: dict = Depends(require_admin)
):
    """
    Get all feedback (Admin only)
    """
    db = get_database()
    
    query = {}
    if status_filter:
        query["status"] = status_filter
    
    feedbacks = list(db.feedback.find(query).sort("created_at", -1))
    
    feedback_list = []
    for fb in feedbacks:
        feedback_list.append(FeedbackResponse(
            id=str(fb["_id"]),
            user_id=str(fb["user_id"]),
            username=fb["username"],
            feedback_type=fb["feedback_type"],
            subject=fb["subject"],
            message=fb["message"],
            rating=fb.get("rating"),
            status=fb.get("status", "pending"),
            created_at=fb["created_at"],
            reviewed_at=fb.get("reviewed_at"),
            admin_response=fb.get("admin_response")
        ))
    
    return FeedbackList(feedbacks=feedback_list, total=len(feedback_list))


@router.put("/{feedback_id}/respond", response_model=FeedbackResponse)
async def respond_to_feedback(
    feedback_id: str,
    response_text: str = Query(..., description="Admin response text"),
    new_status: str = Query("reviewed", description="New status: reviewed or resolved"),
    admin: dict = Depends(require_admin)
):
    """
    Respond to feedback (Admin only)
    """
    db = get_database()
    
    try:
        obj_id = ObjectId(feedback_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid feedback ID")
    
    result = db.feedback.find_one_and_update(
        {"_id": obj_id},
        {
            "$set": {
                "admin_response": response_text,
                "status": new_status,
                "reviewed_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    logger.info(f"Admin {admin['username']} responded to feedback {feedback_id}")
    
    return FeedbackResponse(
        id=str(result["_id"]),
        user_id=str(result["user_id"]),
        username=result["username"],
        feedback_type=result["feedback_type"],
        subject=result["subject"],
        message=result["message"],
        rating=result.get("rating"),
        status=result.get("status", "pending"),
        created_at=result["created_at"],
        reviewed_at=result.get("reviewed_at"),
        admin_response=result.get("admin_response")
    )


@router.delete("/{feedback_id}", response_model=MessageResponse)
async def delete_feedback(
    feedback_id: str,
    admin: dict = Depends(require_admin)
):
    """
    Delete feedback (Admin only)
    """
    db = get_database()
    
    try:
        obj_id = ObjectId(feedback_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid feedback ID")
    
    result = db.feedback.delete_one({"_id": obj_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    logger.info(f"Admin {admin['username']} deleted feedback {feedback_id}")
    
    return MessageResponse(message="Feedback deleted successfully")


@router.get("/stats")
async def get_feedback_stats(
    admin: dict = Depends(require_admin)
):
    """
    Get feedback statistics (Admin only)
    """
    db = get_database()
    
    total = db.feedback.count_documents({})
    pending = db.feedback.count_documents({"status": "pending"})
    reviewed = db.feedback.count_documents({"status": "reviewed"})
    resolved = db.feedback.count_documents({"status": "resolved"})
    
    # Get average rating
    pipeline = [
        {"$match": {"rating": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
    ]
    avg_result = list(db.feedback.aggregate(pipeline))
    avg_rating = round(avg_result[0]["avg_rating"], 1) if avg_result else None
    
    return {
        "total": total,
        "pending": pending,
        "reviewed": reviewed,
        "resolved": resolved,
        "average_rating": avg_rating
    }
