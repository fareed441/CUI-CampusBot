"""
Initialize and populate the vector database with CUI data
Run this script once to set up the database before starting the chatbot
Uses FREE BAAI BGE embeddings (no API key needed, no quotas!)
"""

from load_cui_data import CUIDataLoader
from vector_store_free import FreeVectorStoreManager
from config import (
    DATA_DIRECTORY,
    CHUNK_SIZE,
    CHUNK_OVERLAP
)

def initialize_database():
    """Initialize and populate the vector database"""
    
    print("\n" + "="*60)
    print("CUI Campus Bot - Database Initialization")
    print("="*60)
    
    try:
        # Step 1: Load data
        print("\n[Step 1/3] Loading CUI data...")
        data_loader = CUIDataLoader(
            data_directory=DATA_DIRECTORY,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        
        documents = data_loader.load_all_data()
        
        if not documents:
            print("✗ No documents loaded! Check your data directory.")
            return False
        
        print(f"✓ Loaded {len(documents)} document chunks")
        
        # Step 2: Initialize vector store (FREE - no API key needed!)
        print("\n[Step 2/3] Initializing FREE vector store...")
        print("Using BAAI BGE embeddings (no quotas, runs locally)")
        vector_store = FreeVectorStoreManager(
            collection_name="cui_campus_bot",
            persist_directory="chroma_db"
        )
        
        # Step 3: Add documents to vector store
        print("\n[Step 3/3] Adding documents to vector database...")
        print("This may take a few minutes...")
        
        vector_store.add_documents(documents, batch_size=50, show_progress=True)
        
        # Verify
        stats = vector_store.get_collection_stats()
        
        print("\n" + "="*60)
        print("DATABASE INITIALIZATION COMPLETE!")
        print("="*60)
        print(f"Total documents indexed: {stats['total_documents']}")
        print(f"Collection: {stats['collection_name']}")
        print(f"Status: {stats['status']}")
        print("="*60)
        
        # Test retrieval
        print("\n[Test] Testing document retrieval...")
        test_results = vector_store.similarity_search("What is CUI?", k=3)
        
        if test_results:
            print(f"✓ Retrieval test successful! Found {len(test_results)} documents")
            print("\nSample result:")
            print(f"  Category: {test_results[0].metadata.get('category')}")
            print(f"  Content: {test_results[0].page_content[:150]}...")
        else:
            print("⚠ Warning: No documents retrieved in test")
        
        print("\n✓ You can now run: python app.py")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error during initialization: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = initialize_database()
    
    if not success:
        print("\n⚠ Database initialization failed!")
        print("Please check:")
        print("1. cui_chatbot_data folder exists and contains JSON/PDF files")
        print("2. You have read permissions for the data directory")
        print("3. All required packages are installed")
    else:
        print("\n🎉 Ready to start the chatbot!")
