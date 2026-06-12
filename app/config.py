"""
CUI CampusBot - Configuration Module
Environment variables and application settings
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# ===========================================
# Application Settings
# ===========================================
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# ===========================================
# MongoDB Configuration
# ===========================================
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "cui_campusbot_db")

# ===========================================
# JWT Configuration
# ===========================================
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY or JWT_SECRET_KEY == "your-super-secret-key-change-in-production":
    if DEBUG:
        import secrets as _secrets
        JWT_SECRET_KEY = _secrets.token_hex(32)
    else:
        raise RuntimeError("JWT_SECRET_KEY must be set for production use")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# ===========================================
# File Upload Configuration
# ===========================================
ALLOWED_FILE_TYPES = ["pdf", "docx", "txt"]
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

# ===========================================
# RAG Configuration
# ===========================================
CHROMA_PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIRECTORY", "chroma_db")
# Use multilingual BGE-M3 for English, Urdu, Roman Urdu support
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# Multilingual Support
SUPPORTED_LANGUAGES = ["en", "ur", "roman_urdu"]
DEFAULT_LANGUAGE = "en"

# ===========================================
# Perplexity LLM Configuration
# ===========================================
PPLX_API_KEY = os.getenv("PPLX_API_KEY", "")
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")

# ===========================================
# Application Settings
# ===========================================
APP_NAME = "CUI CampusBot"
APP_VERSION = "2.0.0"

# ===========================================
# Logging
# ===========================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "cui_campusbot.log")


def get_settings():
    """Return all settings as a dictionary"""
    return {
        "mongodb_uri": MONGODB_URI,
        "mongodb_db_name": MONGODB_DB_NAME,
        "jwt_algorithm": JWT_ALGORITHM,
        "access_token_expire_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        "allowed_file_types": ALLOWED_FILE_TYPES,
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "chroma_persist_directory": CHROMA_PERSIST_DIRECTORY,
        "embedding_model": EMBEDDING_MODEL,
        "debug": DEBUG,
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
    }
