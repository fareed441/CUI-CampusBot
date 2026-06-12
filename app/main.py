"""
CUI CampusBot - FastAPI Application Entry Point
OAuth2 + JWT + MongoDB + RAG Chatbot
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from typing import Optional
import logging
from datetime import datetime
import os
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cui_campusbot.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Import configuration and database
from app.config import APP_NAME, APP_VERSION, DEBUG
from app.database import db, get_database
from app.auth import create_default_admin, decode_access_token, get_user_by_id
from app.config import DEBUG

# Import routers
from app.routes import auth_router, document_router, admin_router, chat_router, feedback_router

# Import timetable API router (PDF-based)
try:
    from api.timetable_api import router as timetable_router
    TIMETABLE_API_AVAILABLE = True
    logger.info("[OK] Timetable API router imported")
except ImportError as e:
    TIMETABLE_API_AVAILABLE = False
    logger.warning(f"[WARN] Timetable API not available: {e}")

# Get base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ===========================================
# Application Lifespan
# ===========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown events
    
    STARTUP FLOW:
    1. Connect to MongoDB (primary data source)
    2. Create default admin user
    3. Sync MongoDB documents to ChromaDB (rebuild embeddings)
    4. Initialize RAG query handler
    """
    # Startup
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info("="*60)
    
    # Step 1: Connect to MongoDB
    if db.connect():
        logger.info("[OK] MongoDB connected - Primary data source ready")
        
        # Step 2: Create default admin if not exists
        create_default_admin()
        
        # Step 3: Sync MongoDB documents to ChromaDB
        try:
            from app.rag.startup_sync import sync_mongodb_to_chromadb
            logger.info("[SYNC] Starting MongoDB to ChromaDB sync...")
            sync_result = sync_mongodb_to_chromadb(force_rebuild=False)
            logger.info(f"[OK] Sync complete: {sync_result['newly_processed']} new, {sync_result['already_synced']} cached")
        except Exception as e:
            logger.warning(f"[WARN] MongoDB to ChromaDB sync: {str(e)}")
        
        # Step 4: Initialize RAG query handler
        try:
            from app.rag.query_handler import get_rag_handler
            get_rag_handler()
            logger.info("[OK] Multilingual RAG handler initialized")
        except Exception as e:
            logger.warning(f"[WARN] RAG handler initialization: {str(e)}")
            
    else:
        logger.error("[ERROR] MongoDB connection failed - Application may not work correctly")
    
    logger.info("="*60)
    logger.info(f"[OK] {APP_NAME} v{APP_VERSION} is ready!")
    logger.info("="*60)
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    db.close()


# ===========================================
# FastAPI Application
# ===========================================

app = FastAPI(
    title=APP_NAME,
    description="CUI CampusBot - Intelligent RAG-based Q&A system for COMSATS University Islamabad, Vehari Campus",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None
)

SECURE_ADMIN_LOGIN_PATH = "/secure-admin-portal/login"
SECURE_ADMIN_DASHBOARD_PATH = "/secure-admin-portal/dashboard"


def _get_user_from_cookie(request: Request) -> Optional[dict]:
    token = request.cookies.get("cui_access_token")
    if not token:
        return None

    token_data = decode_access_token(token)
    if token_data is None or token_data.exp < datetime.utcnow():
        return None

    user = get_user_by_id(token_data.sub)
    if not user or not user.get("is_active", True):
        return None

    return user



# ===========================================
# Static Files and Templates
# ===========================================

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ===========================================
# CORS Middleware
# ===========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================
# Exception Handlers
# ===========================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ===========================================
# Include Routers
# ===========================================

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(feedback_router)

# Include timetable routers if available
if TIMETABLE_API_AVAILABLE:
    app.include_router(timetable_router)
    logger.info("[OK] Timetable API endpoints mounted")


# ===========================================
# Root Endpoints
# ===========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Home page - serve index.html
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get(SECURE_ADMIN_LOGIN_PATH, response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Login page
    """
    return templates.TemplateResponse("login_new.html", {"request": request})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """
    Chat page (requires authentication via JS)
    """
    return templates.TemplateResponse("chat_new.html", {"request": request})


@app.get("/timetable", response_class=HTMLResponse)
async def timetable_page(request: Request):
    """
    Timetable page
    """
    return templates.TemplateResponse("timetable.html", {"request": request})


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request):
    """
    Feedback page
    """
    return templates.TemplateResponse("feedback.html", {"request": request})


@app.get(SECURE_ADMIN_DASHBOARD_PATH, response_class=HTMLResponse)
async def admin_page(request: Request):
    """
    Admin dashboard (requires admin auth via JS)
    """
    user = _get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url=SECURE_ADMIN_LOGIN_PATH, status_code=302)
    if user.get("role") not in ("admin", "super_admin"):
        return HTMLResponse(content="403 Forbidden", status_code=403)
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/admin/register", response_class=HTMLResponse)
async def admin_register_page(request: Request):
    """Invite-based admin registration page."""
    return templates.TemplateResponse("admin_register.html", {"request": request})


@app.get("/knowledge-base")
async def knowledge_base_page():
    """
    Redirect knowledge base to admin dashboard
    """
    return RedirectResponse(url="/", status_code=302)


@app.get("/api/stats")
async def get_system_stats():
    """
    Get system statistics
    """
    database = get_database()
    
    if not database:
        return {"error": "Database not connected"}
    
    users_count = database.users.count_documents({})
    documents_count = database.documents.count_documents({})
    processed_docs = database.documents.count_documents({"status": "processed"})
    feedback_count = database.feedback.count_documents({})
    chat_count = database.chat_history.count_documents({})
    
    total_chunks = 0
    for doc in database.documents.find({"chunk_count": {"$exists": True}}):
        total_chunks += doc.get("chunk_count", 0)
    
    return {
        "users": users_count,
        "documents": {
            "total": documents_count,
            "processed": processed_docs,
            "pending": documents_count - processed_docs
        },
        "knowledge_base": {
            "total_chunks": total_chunks,
            "embedding_model": "BAAI/bge-m3"
        },
        "feedback": feedback_count,
        "chat_messages": chat_count,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api")
async def api_info():
    """
    API information endpoint
    """
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "message": "Welcome to CUI CampusBot API",
        "docs": "/docs" if DEBUG else "Disabled in production",
        "endpoints": {
            "auth": "/api/auth",
            "documents": "/api/documents",
            "chat": "/api/chat"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    db_health = db.health_check()
    
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "database": db_health,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/status")
async def api_status():
    """
    API status endpoint
    """
    try:
        from rag_pipeline_free import rag_system
        rag_status = "online" if rag_system else "not initialized"
    except:
        rag_status = "unavailable"
    
    return {
        "api": "online",
        "database": db.health_check()["status"],
        "rag_system": rag_status,
        "timestamp": datetime.utcnow().isoformat()
    }


# ===========================================
# Run with Uvicorn
# ===========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
        workers=1
    )
