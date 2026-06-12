"""
Timetable System Main Application

FastAPI application integrating:
- Timetable API endpoints
- Repeater clash resolution API
- Admin UI for repeater management
- PDF/HTML rendering endpoints
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import API routers
from api.timetable_api import router as timetable_router
from api.repeater_api import router as repeater_router

# Create FastAPI app
app = FastAPI(
    title="CUI Timetable System",
    description="Clash-free timetable system with repeater student clash resolver",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(timetable_router)
app.include_router(repeater_router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to timetable UI."""
    return RedirectResponse(url="/timetable")


@app.get("/timetable", response_class=HTMLResponse)
async def timetable_ui(request: Request):
    """Batch timetable UI."""
    return templates.TemplateResponse("timetable.html", {"request": request})


@app.get("/admin/repeater", response_class=HTMLResponse)
async def repeater_admin(request: Request):
    """Repeater clash resolver admin UI."""
    return templates.TemplateResponse("repeater_admin.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint with MongoDB status."""
    from api.mongodb_timetable import get_timetable_store
    store = get_timetable_store()
    db_health = store.health_check()
    return {
        "status": "healthy" if db_health.get("connected") else "degraded",
        "service": "timetable-system",
        "mongodb": db_health
    }


@app.get("/api/docs")
async def api_docs():
    """API documentation info."""
    return {
        "endpoints": {
            "timetable": {
                "GET /api/timetable/health": "Health check with MongoDB status",
                "GET /api/timetable/batches": "List all batches from MongoDB",
                "GET /api/timetable/batch/{batch_section}": "Get batch schedule (normalized)",
                "GET /api/timetable/batch/{batch_section}/pdf": "Generate PDF for batch",
                "GET /api/timetable/batch/{batch_section}/offerings": "Get batch in offerings format",
                "GET /api/timetable/export/all.pdf": "Export all batches as single PDF",
                "GET /api/timetable/offerings": "List all offerings",
                "POST /api/timetable/render-pdf": "Generate PDF (legacy)",
                "GET /api/timetable/render-html/{batch}": "Generate HTML timetable",
            },
            "repeater": {
                "POST /api/repeater/suggest": "Layer-1 fast alternative suggestions",
                "POST /api/repeater/solve": "Layer-2 CP-SAT multi-course solver",
                "GET /api/repeater/student/{id}/schedule": "Get student schedule",
                "POST /api/repeater/student/{id}/enroll": "Enroll in offering",
                "DELETE /api/repeater/student/{id}/enroll/{oid}": "Remove from offering",
            }
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "timetable_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
