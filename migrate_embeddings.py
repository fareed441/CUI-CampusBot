"""
BGE-M3 Embedding Migration Script
Migrates from bge-small-en-v1.5 to bge-m3 for multilingual support

This script:
1. Backs up the existing ChromaDB
2. Clears old embeddings (incompatible with new model)
3. Re-embeds all documents from MongoDB with BGE-M3
4. Validates the migration

Run: python migrate_embeddings.py
"""

import os
import sys
import shutil
from datetime import datetime
from pymongo import MongoClient
from gridfs import GridFS

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vector_store_free import FreeVectorStoreManager, DEFAULT_MODEL
from langchain_core.documents import Document

# Configuration
CHROMA_DB_PATH = "chroma_db"
BACKUP_PATH = f"chroma_db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://fareedanwar099:FareedBhatti%407724099@cuibotcluster.wao3ncd.mongodb.net/?retryWrites=true&w=majority&appName=CUIBotCluster")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "cui_campusbot_db")


def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")


def backup_existing_db():
    """Backup existing ChromaDB before migration"""
    if os.path.exists(CHROMA_DB_PATH):
        print(f"📦 Backing up existing ChromaDB to: {BACKUP_PATH}")
        shutil.copytree(CHROMA_DB_PATH, BACKUP_PATH)
        print(f"✓ Backup created successfully")
        return True
    else:
        print("⚠ No existing ChromaDB found, skipping backup")
        return False


def clear_old_embeddings():
    """Clear old embeddings (incompatible with new model)"""
    if os.path.exists(CHROMA_DB_PATH):
        print(f"🗑️  Clearing old embeddings from: {CHROMA_DB_PATH}")
        shutil.rmtree(CHROMA_DB_PATH)
        print(f"✓ Old embeddings cleared")
    os.makedirs(CHROMA_DB_PATH, exist_ok=True)


def get_documents_from_mongodb():
    """Fetch all documents from MongoDB for re-embedding"""
    print_header("Fetching Documents from MongoDB")
    
    try:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DB_NAME]
        fs = GridFS(db)
        
        documents = []
        
        # Get documents from GridFS
        print("Fetching from GridFS...")
        for grid_file in fs.find():
            try:
                content = grid_file.read().decode('utf-8')
                metadata = {
                    "source": grid_file.filename,
                    "file_id": str(grid_file._id),
                    "upload_date": str(grid_file.upload_date)
                }
                if hasattr(grid_file, 'metadata') and grid_file.metadata:
                    metadata.update(grid_file.metadata)
                
                documents.append(Document(
                    page_content=content,
                    metadata=metadata
                ))
            except Exception as e:
                print(f"  ⚠ Error reading file {grid_file.filename}: {str(e)}")
        
        # Also get from knowledge_base collection if exists
        if 'knowledge_base' in db.list_collection_names():
            print("Fetching from knowledge_base collection...")
            for doc in db.knowledge_base.find():
                content = doc.get('content', '')
                if content:
                    documents.append(Document(
                        page_content=content,
                        metadata={
                            "source": doc.get('filename', 'unknown'),
                            "category": doc.get('category', 'general'),
                            "doc_id": str(doc.get('_id', ''))
                        }
                    ))
        
        print(f"✓ Found {len(documents)} documents to embed")
        client.close()
        return documents
        
    except Exception as e:
        print(f"✗ Error connecting to MongoDB: {str(e)}")
        return []


def chunk_documents(documents, chunk_size=1000, chunk_overlap=200):
    """Split documents into chunks for embedding"""
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    
    print_header(f"Chunking Documents (size={chunk_size}, overlap={chunk_overlap})")
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = []
    for doc in documents:
        doc_chunks = text_splitter.split_documents([doc])
        chunks.extend(doc_chunks)
    
    print(f"✓ Created {len(chunks)} chunks from {len(documents)} documents")
    return chunks


def migrate_to_bge_m3():
    """Main migration function"""
    print_header("BGE-M3 Multilingual Embedding Migration")
    print(f"Target Model: {DEFAULT_MODEL}")
    print(f"Features: English, Urdu, Roman Urdu + 100 languages")
    
    # Step 1: Backup existing database
    print_header("Step 1: Backup Existing Database")
    backup_existing_db()
    
    # Step 2: Clear old embeddings
    print_header("Step 2: Clear Old Embeddings")
    clear_old_embeddings()
    
    # Step 3: Fetch documents from MongoDB
    documents = get_documents_from_mongodb()
    
    if not documents:
        print("\n⚠ No documents found in MongoDB!")
        print("The vector store will be empty. Upload documents via admin panel.")
        
        # Still initialize the vector store with new model
        print_header("Step 4: Initialize Empty Vector Store")
        vector_store = FreeVectorStoreManager()
        print("✓ Vector store initialized with BGE-M3 (empty)")
        return True
    
    # Step 4: Chunk documents
    chunks = chunk_documents(documents)
    
    # Step 5: Initialize new vector store with BGE-M3 and embed
    print_header("Step 5: Embedding with BGE-M3")
    print("⏳ This may take several minutes on first run (downloading ~2.3GB model)...")
    
    try:
        vector_store = FreeVectorStoreManager()
        
        if chunks:
            vector_store.add_documents(chunks)
            print(f"\n✓ Successfully migrated {len(chunks)} chunks to BGE-M3!")
        else:
            print("✓ Vector store initialized (no chunks to add)")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Migration failed: {str(e)}")
        print(f"\nRollback: Restore from backup at {BACKUP_PATH}")
        return False


def verify_migration():
    """Verify migration was successful"""
    print_header("Verifying Migration")
    
    try:
        # Test initializing vector store
        vector_store = FreeVectorStoreManager()
        
        # Test a query
        test_queries = [
            "What are the admission requirements?",
            "داخلے کے تقاضے کیا ہیں؟",
            "Admission ke liye kya chahiye?"
        ]
        
        print("Testing multilingual search...")
        for query in test_queries:
            results = vector_store.similarity_search(query, k=2)
            print(f"  Query: {query[:40]}... → {len(results)} results")
        
        print("\n✓ Migration verified successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Verification failed: {str(e)}")
        return False


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║  CUI CampusBot - BGE-M3 Embedding Migration              ║
║  Upgrading to Multilingual Support                       ║
╚══════════════════════════════════════════════════════════╝
""")
    
    # Confirm with user
    print("This script will:")
    print("  1. Backup existing ChromaDB")
    print("  2. Clear old embeddings (bge-small-en is incompatible)")
    print("  3. Download BGE-M3 model (~2.3GB on first run)")
    print("  4. Re-embed all documents from MongoDB")
    print()
    
    response = input("Continue? (y/n): ").strip().lower()
    
    if response == 'y':
        success = migrate_to_bge_m3()
        
        if success:
            verify_migration()
            print("\n🎉 Migration complete! Restart the server to use BGE-M3.")
        else:
            print("\n❌ Migration failed. Check errors above.")
            sys.exit(1)
    else:
        print("Migration cancelled.")
