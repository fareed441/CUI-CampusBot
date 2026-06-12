"""
CUI CampusBot - App Package
"""

from app.config import get_settings
from app.database import db, get_database
from app.models import *
from app.auth import create_default_admin

__all__ = [
    "get_settings",
    "db",
    "get_database",
    "create_default_admin"
]
