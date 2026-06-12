"""
MongoDB-backed Timetable Store

Provides database operations for timetable entries stored in MongoDB.
Collection: timetable_entries

Schema:
{
    timetable_id: str,
    batch_section: str (e.g., "FA22-BCS-8A"),
    course: str,
    teacher: str,
    day: int (0-4 for Mon-Fri),
    slotStart: int (1-6),
    slotSpan: int (1 or 2),
    room: str (optional),
    type: "LEC" | "LAB"
}
"""
import re
import logging
from typing import List, Dict, Optional, Any
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime
import certifi

logger = logging.getLogger(__name__)


# =========================================================
# Batch Code Normalization
# =========================================================
def normalize_batch_code(batch_code: str) -> str:
    """
    Normalize batch code for consistent matching.
    
    Handles variations like:
    - FA22-BCS-8A
    - fa22-bcs-8a
    - FA22 BCS 8A
    - fa22  bcs  8a
    
    Returns uppercase, hyphen-separated code.
    """
    if not batch_code:
        return ""
    
    # Trim whitespace
    result = batch_code.strip()
    
    # Convert to uppercase
    result = result.upper()
    
    # Replace spaces, underscores with hyphens
    result = re.sub(r'[\s_]+', '-', result)
    
    # Collapse multiple hyphens to single hyphen
    result = re.sub(r'-+', '-', result)
    
    # Remove leading/trailing hyphens
    result = result.strip('-')
    
    return result


# =========================================================
# Slot Time Labels
# =========================================================
SLOT_TIMES = {
    1: {"label": "8:30-10:00", "start": "08:30", "end": "10:00"},
    2: {"label": "10:00-11:30", "start": "10:00", "end": "11:30"},
    3: {"label": "11:30-1:00", "start": "11:30", "end": "13:00"},
    4: {"label": "1:30-3:00", "start": "13:30", "end": "15:00"},
    5: {"label": "3:00-4:30", "start": "15:00", "end": "16:30"},
    6: {"label": "4:30-6:00", "start": "16:30", "end": "18:00"},
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DAY_FULL_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


# =========================================================
# MongoDB Timetable Store
# =========================================================
class MongoDBTimetableStore:
    """
    MongoDB-backed timetable store with singleton pattern.
    """
    
    _instance: Optional['MongoDBTimetableStore'] = None
    _client: Optional[MongoClient] = None
    _db = None
    _collection = None
    _connected = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        pass
    
    def connect(self, mongodb_uri: str = None, db_name: str = None) -> bool:
        """
        Establish MongoDB connection.
        
        Args:
            mongodb_uri: MongoDB connection string
            db_name: Database name
            
        Returns:
            True if connected successfully
        """
        if self._connected:
            return True
        
        # Get from environment if not provided
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        if not mongodb_uri:
            mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        if not db_name:
            db_name = os.getenv("MONGODB_DB_NAME", "cui_campusbot_db")
        
        try:
            self._client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                tlsCAFile=certifi.where()
            )
            # Test connection
            self._client.admin.command('ping')
            self._db = self._client[db_name]
            self._collection = self._db.timetable_entries
            
            # Create indexes
            self._create_indexes()
            
            self._connected = True
            logger.info(f"[OK] Connected to MongoDB timetable store: {db_name}")
            return True
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"[ERROR] MongoDB connection failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error: {str(e)}")
            return False
    
    def _create_indexes(self):
        """Create required indexes for efficient queries."""
        try:
            # Compound index for batch lookups
            self._collection.create_index([
                ("timetable_id", ASCENDING),
                ("batch_section", ASCENDING)
            ])
            
            # Single index on batch_section
            self._collection.create_index("batch_section")
            
            # Index on timetable_id
            self._collection.create_index("timetable_id")
            
            logger.info("[OK] Created indexes on timetable_entries collection")
        except Exception as e:
            logger.warning(f"Index creation warning: {str(e)}")
    
    @property
    def collection(self):
        """Get the timetable_entries collection."""
        if not self._connected:
            self.connect()
        return self._collection
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MongoDB."""
        return self._connected and self._collection is not None
    
    def ensure_connected(self) -> bool:
        """Ensure connection is established."""
        if not self._connected:
            return self.connect()
        return True
    
    # =========================================================
    # Batch Operations
    # =========================================================
    
    def get_all_batches(self, timetable_id: str = None) -> List[str]:
        """
        Get all distinct batch sections.
        
        Args:
            timetable_id: Optional filter by timetable ID
            
        Returns:
            List of batch section codes
        """
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot get batches: MongoDB not connected")
            return []
        
        query = {}
        if timetable_id:
            query["timetable_id"] = timetable_id
        
        try:
            batches = self.collection.distinct("batch_section", query)
            return sorted(batches)
        except Exception as e:
            logger.error(f"Error getting batches: {e}")
            return []
    
    def get_batch_entries(self, batch_section: str, timetable_id: str = None) -> List[Dict]:
        """
        Get all timetable entries for a batch.
        
        Args:
            batch_section: Batch code (will be normalized)
            timetable_id: Optional filter by timetable ID
            
        Returns:
            List of entry documents
        """
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot get batch entries: MongoDB not connected")
            return []
        
        # Normalize batch code
        normalized = normalize_batch_code(batch_section)
        
        # Build query
        query = {"batch_section": normalized}
        if timetable_id:
            query["timetable_id"] = timetable_id
        
        try:
            entries = list(self.collection.find(query))
            
            # If not found with exact match, try case-insensitive regex
            if not entries:
                query["batch_section"] = {"$regex": f"^{re.escape(normalized)}$", "$options": "i"}
                entries = list(self.collection.find(query))
            
            # Convert ObjectId to string
            for entry in entries:
                if "_id" in entry:
                    entry["_id"] = str(entry["_id"])
            
            return entries
        except Exception as e:
            logger.error(f"Error getting batch entries: {e}")
            return []
    
    def get_batch_timetable(self, batch_section: str, timetable_id: str = None) -> Optional[Dict]:
        """
        Get formatted timetable data for a batch.
        
        Args:
            batch_section: Batch code
            timetable_id: Optional filter
            
        Returns:
            Formatted timetable data for UI rendering:
            {
                batch: str,
                days: ["Mon", "Tue", ...],
                slots: [{slot: 1, label: "8:30-10:00"}, ...],
                entries: [{day: 0, slotStart: 1, slotSpan: 1, course, teacher, room, type}, ...]
            }
        """
        entries = self.get_batch_entries(batch_section, timetable_id)
        
        if not entries:
            return None
        
        # Get actual batch code from first entry (normalized form)
        actual_batch = entries[0].get("batch_section", normalize_batch_code(batch_section))
        
        # Format slots info
        slots_info = [
            {"slot": slot, "label": info["label"]}
            for slot, info in sorted(SLOT_TIMES.items())
        ]
        
        # Format entries
        formatted_entries = []
        for entry in entries:
            formatted_entries.append({
                "day": entry.get("day", 0),
                "slotStart": entry.get("slotStart", 1),
                "slotSpan": entry.get("slotSpan", 1),
                "course": entry.get("course", ""),
                "teacher": entry.get("teacher", ""),
                "room": entry.get("room", ""),
                "type": entry.get("type", "LEC")
            })
        
        return {
            "batch": actual_batch,
            "days": DAY_NAMES,
            "slots": slots_info,
            "entries": formatted_entries
        }
    
    # =========================================================
    # CRUD Operations
    # =========================================================
    
    def insert_entry(self, entry: Dict) -> bool:
        """Insert a single timetable entry."""
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot insert entry: MongoDB not connected")
            return False
        
        # Normalize batch_section
        if "batch_section" in entry:
            entry["batch_section"] = normalize_batch_code(entry["batch_section"])
        
        entry["created_at"] = datetime.utcnow()
        
        try:
            self.collection.insert_one(entry)
            return True
        except Exception as e:
            logger.error(f"Error inserting entry: {e}")
            return False
    
    def insert_entries(self, entries: List[Dict]) -> int:
        """
        Insert multiple timetable entries.
        
        Returns:
            Number of entries inserted
        """
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot insert entries: MongoDB not connected")
            return 0
        
        if not entries:
            return 0
        
        # Normalize batch codes
        timestamp = datetime.utcnow()
        for entry in entries:
            if "batch_section" in entry:
                entry["batch_section"] = normalize_batch_code(entry["batch_section"])
            entry["created_at"] = timestamp
        
        try:
            result = self.collection.insert_many(entries)
            return len(result.inserted_ids)
        except Exception as e:
            logger.error(f"Error inserting entries: {e}")
            return 0
    
    def delete_batch_entries(self, batch_section: str, timetable_id: str = None) -> int:
        """
        Delete all entries for a batch.
        
        Returns:
            Number of entries deleted
        """
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot delete entries: MongoDB not connected")
            return 0
        
        query = {"batch_section": normalize_batch_code(batch_section)}
        if timetable_id:
            query["timetable_id"] = timetable_id
        
        try:
            result = self.collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting entries: {e}")
            return 0
    
    def delete_timetable(self, timetable_id: str) -> int:
        """
        Delete all entries for a timetable.
        
        Returns:
            Number of entries deleted
        """
        if not self.ensure_connected() or self._collection is None:
            logger.warning("Cannot delete timetable: MongoDB not connected")
            return 0
        
        try:
            result = self.collection.delete_many({"timetable_id": timetable_id})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting timetable: {e}")
            return 0
    
    # =========================================================
    # Stats and Health
    # =========================================================
    
    def get_stats(self) -> Dict:
        """Get collection statistics."""
        if not self.ensure_connected() or self._collection is None:
            return {
                "total_entries": 0,
                "total_batches": 0,
                "total_timetables": 0,
                "status": "disconnected",
                "error": "MongoDB not connected"
            }
        
        try:
            total = self.collection.count_documents({})
            batches = len(self.get_all_batches())
            timetables = len(self.collection.distinct("timetable_id"))
            
            return {
                "total_entries": total,
                "total_batches": batches,
                "total_timetables": timetables,
                "status": "connected"
            }
        except Exception as e:
            return {
                "total_entries": 0,
                "total_batches": 0,
                "total_timetables": 0,
                "status": "error",
                "error": str(e)
            }
    
    def health_check(self) -> Dict:
        """Check MongoDB connection health."""
        try:
            if self._client:
                self._client.admin.command('ping')
                return {"status": "healthy", "connected": True}
        except Exception as e:
            return {"status": "unhealthy", "connected": False, "error": str(e)}
        
        return {"status": "not_connected", "connected": False}


# =========================================================
# Global Instance
# =========================================================
_timetable_store: Optional[MongoDBTimetableStore] = None


def get_timetable_store() -> MongoDBTimetableStore:
    """Get the global timetable store instance."""
    global _timetable_store
    if _timetable_store is None:
        _timetable_store = MongoDBTimetableStore()
    return _timetable_store
