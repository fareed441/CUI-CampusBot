"""
CUI CampusBot - Database Module
MongoDB connection, collections, indexes, and GridFS setup
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from gridfs import GridFS
from datetime import datetime
from typing import Optional
import logging
import certifi

from app.config import MONGODB_URI, MONGODB_DB_NAME

logger = logging.getLogger(__name__)


class Database:
    """
    MongoDB Database Manager
    Handles connection, collections, indexes, and GridFS
    """
    
    _instance: Optional['Database'] = None
    _client: Optional[MongoClient] = None
    _db = None
    _gridfs = None
    
    def __new__(cls):
        """Singleton pattern - ensure only one database instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def connect(self) -> bool:
        """
        Establish MongoDB connection
        Returns True if successful, False otherwise
        """
        try:
            # Connect to MongoDB Atlas with SSL certificates
            self._client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                tlsCAFile=certifi.where()
            )
            # Test connection
            self._client.admin.command('ping')
            self._db = self._client[MONGODB_DB_NAME]
            self._gridfs = GridFS(self._db)
            
            logger.info(f"[OK] Connected to MongoDB: {MONGODB_DB_NAME}")
            
            # Create indexes
            self._create_indexes()
            
            return True
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"[ERROR] MongoDB connection failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Unexpected database error: {str(e)}")
            return False
    
    def _create_indexes(self):
        """Create required indexes for all collections"""
        try:
            # Users collection indexes
            self._db.users.create_index("email", unique=True)
            self._db.users.create_index("username", unique=True)
            logger.info("[OK] Created indexes on 'users' collection")
            
            # Documents collection indexes
            self._db.documents.create_index([("upload_date", DESCENDING)])
            self._db.documents.create_index("status")
            self._db.documents.create_index("uploaded_by")
            logger.info("[OK] Created indexes on 'documents' collection")
            
            # Chat history collection indexes
            self._db.chat_history.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
            self._db.chat_history.create_index([("timestamp", DESCENDING)])
            logger.info("[OK] Created indexes on 'chat_history' collection")

            # Admin invites collection indexes
            self._db.admin_invites.create_index("token", unique=True)
            self._db.admin_invites.create_index("token_hash", unique=True, sparse=True)
            self._db.admin_invites.create_index("email")
            self._db.admin_invites.create_index("expires_at")
            self._db.admin_invites.create_index("used")
            logger.info("[OK] Created indexes on 'admin_invites' collection")
            
        except Exception as e:
            logger.warning(f"Index creation warning: {str(e)}")
    
    @property
    def client(self) -> MongoClient:
        """Get MongoDB client"""
        if self._client is None:
            self.connect()
        return self._client
    
    @property
    def db(self):
        """Get database instance"""
        if self._db is None:
            self.connect()
        return self._db
    
    @property
    def gridfs(self) -> GridFS:
        """Get GridFS instance for file storage"""
        if self._gridfs is None:
            self.connect()
        return self._gridfs
    
    # ===========================================
    # Collection Accessors
    # ===========================================
    
    @property
    def users(self):
        """Users collection"""
        return self.db.users
    
    @property
    def documents(self):
        """Documents collection"""
        return self.db.documents
    
    @property
    def chat_history(self):
        """Chat history collection"""
        return self.db.chat_history
    
    # ===========================================
    # GridFS Operations
    # ===========================================
    
    def store_file(self, file_data: bytes, filename: str, content_type: str, metadata: dict = None) -> str:
        """
        Store file in GridFS
        Returns: GridFS file ID as string
        """
        file_id = self.gridfs.put(
            file_data,
            filename=filename,
            content_type=content_type,
            metadata=metadata or {},
            upload_date=datetime.utcnow()
        )
        logger.info(f"[OK] Stored file in GridFS: {filename} (ID: {file_id})")
        return str(file_id)
    
    def get_file(self, file_id: str) -> Optional[bytes]:
        """
        Retrieve file from GridFS
        Returns: File data as bytes, or None if not found
        """
        from bson import ObjectId
        try:
            grid_out = self.gridfs.get(ObjectId(file_id))
            return grid_out.read()
        except Exception as e:
            logger.error(f"[ERROR] Failed to retrieve file {file_id}: {str(e)}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """
        Delete file from GridFS
        Returns: True if successful
        """
        from bson import ObjectId
        try:
            self.gridfs.delete(ObjectId(file_id))
            logger.info(f"[OK] Deleted file from GridFS: {file_id}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete file {file_id}: {str(e)}")
            return False
    
    # ===========================================
    # Health Check
    # ===========================================
    
    def health_check(self) -> dict:
        """Check database health and return status"""
        try:
            self._client.admin.command('ping')
            return {
                "status": "healthy",
                "database": MONGODB_DB_NAME,
                "collections": {
                    "users": self.users.count_documents({}),
                    "documents": self.documents.count_documents({}),
                    "chat_history": self.chat_history.count_documents({})
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    def close(self):
        """Close database connection"""
        if self._client:
            self._client.close()
            logger.info("[OK] MongoDB connection closed")


# ===========================================
# Global Database Instance
# ===========================================
db = Database()


def get_database() -> Database:
    """Get database instance (dependency injection)"""
    if not db._client:
        db.connect()
    return db
