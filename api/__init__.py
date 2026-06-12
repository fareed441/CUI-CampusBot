"""API package exports.

Only the PDF-based timetable router is intentionally exported.
"""

from .timetable_api import router as timetable_router

__all__ = ["timetable_router"]
