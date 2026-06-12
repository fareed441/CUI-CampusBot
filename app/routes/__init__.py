"""
CUI CampusBot - Routes Package
Export all routers for FastAPI app
"""

from app.routes.auth_routes import router as auth_router
from app.routes.document_routes import router as document_router, admin_router
from app.routes.chat_routes import router as chat_router
from app.routes.feedback_routes import router as feedback_router

__all__ = ["auth_router", "document_router", "admin_router", "chat_router", "feedback_router"]
