"""
CUI CampusBot - Chat Routes
Public chat endpoints with RAG integration (No login required for students)

Features:
- Multilingual support (English, Urdu, Roman Urdu)
- Automatic language detection
- Response in same language as query
- MongoDB as source of truth
- ChromaDB for vector search
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import logging

from app.models import ChatMessage, ChatResponse, ChatHistory, MessageResponse
from app.dependencies import get_current_user, get_optional_user
from app.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


def get_rag_handler():
    """Get the multilingual RAG handler"""
    try:
        from app.rag.query_handler import get_rag_handler as _get_handler
        return _get_handler()
    except Exception as e:
        logger.error(f"Failed to get RAG handler: {str(e)}")
        raise


# ===========================================
# Chat Endpoint (PUBLIC - No login required)
# ===========================================

@router.post("/", response_model=ChatResponse)
async def send_chat_message(
    chat_message: ChatMessage,
    request: Request
):
    """
    Send a message to the CUI CampusBot (Public - No login required)
    
    Features:
    - Multilingual support (English, Urdu, Roman Urdu)
    - Automatic language detection
    - Response in same language as query
    - Uses MongoDB documents via ChromaDB
    - Stores conversation in chat history (anonymous)
    """
    db = get_database()
    
    try:
        # Get RAG handler
        rag = get_rag_handler()
        
        # Query with multilingual support
        result = rag.query(chat_message.message)
        
        # Extract response data
        answer = result.get("answer", "I apologize, but I couldn't generate a response.")
        language = result.get("language", "en")
        sources_count = result.get("sources_count", 0)
        
        # Store in chat history (anonymous)
        chat_entry = {
            "user_id": "anonymous",
            "username": "Student",
            "question": chat_message.message,
            "answer": answer,
            "language": language,
            "sources_count": sources_count,
            "timestamp": datetime.utcnow(),
            "ip_address": request.client.host if request.client else "unknown"
        }
        db.chat_history.insert_one(chat_entry)
        
        logger.info(f"[OK] Chat response generated (lang: {language})")
        
        return ChatResponse(
            success=True,
            answer=answer,
            sources=[],  # Don't expose internal sources
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
        )


# ===========================================
# Chat History
# ===========================================

@router.get("/history", response_model=List[ChatHistory])
async def get_chat_history(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user's chat history
    """
    db = get_database()
    
    history = list(
        db.chat_history.find({"user_id": str(current_user["_id"])})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    
    return [
        ChatHistory(
            user_id=h["user_id"],
            question=h["question"],
            answer=h["answer"],
            sources=h.get("sources"),
            timestamp=h["timestamp"]
        )
        for h in history
    ]


@router.delete("/history", response_model=MessageResponse)
async def clear_chat_history(
    current_user: dict = Depends(get_current_user)
):
    """
    Clear current user's chat history
    """
    db = get_database()
    
    result = db.chat_history.delete_many({"user_id": str(current_user["_id"])})
    
    logger.info(f"[OK] Chat history cleared for user: {current_user['username']} ({result.deleted_count} messages)")
    
    return MessageResponse(message=f"Deleted {result.deleted_count} messages from history")


# ===========================================
# Quick Chat (For Testing - Admin Only)
# ===========================================

@router.post("/quick")
async def quick_chat(
    message: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Quick chat endpoint for testing (no history storage)
    """
    try:
        rag = get_rag_handler()
        result = rag.query(message)
        
        return {
            "success": True,
            "question": message,
            "answer": result.get("answer", "No response"),
            "sources_count": result.get("sources_count", 0)
        }
        
    except Exception as e:
        logger.error(f"Quick chat error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# ===========================================
# System Status
# ===========================================

@router.get("/status")
async def get_chat_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get RAG system status
    """
    try:
        rag = get_rag_handler()
        status = {
            "handler_initialized": rag is not None,
        }
        return {
            "status": "online",
            "rag_initialized": True,
            "pipeline_status": status,
            "user": current_user["username"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
