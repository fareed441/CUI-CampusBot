"""
CUI CampusBot - RAG Package

Modules:
- ingestion: Document processing for new uploads
- startup_sync: MongoDB → ChromaDB sync on startup
- query_handler: Multilingual RAG query processing
"""

from app.rag.ingestion import (
    process_document,
    delete_document_embeddings,
    rebuild_all_embeddings
)

from app.rag.startup_sync import (
    sync_mongodb_to_chromadb,
    get_vectorstore,
    get_embeddings,
    get_sync_instance
)

from app.rag.query_handler import (
    query_rag,
    detect_language,
    get_rag_handler
)

__all__ = [
    # Ingestion
    "process_document",
    "delete_document_embeddings", 
    "rebuild_all_embeddings",
    # Startup Sync
    "sync_mongodb_to_chromadb",
    "get_vectorstore",
    "get_embeddings",
    "get_sync_instance",
    # Query
    "query_rag",
    "detect_language",
    "get_rag_handler"
]
