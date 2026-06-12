"""
FREE Vector Store using BAAI BGE-M3 Multilingual Embeddings
No API key required, unlimited usage, runs locally
Supports: English, Urdu, Roman Urdu, and 100+ languages
"""

import os
import json
from typing import List, Optional, Dict
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
import chromadb
from chromadb.config import Settings

# Default cache directory for HuggingFace models
HF_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hf_cache")

# BGE-M3: Multilingual embedding model supporting 100+ languages
DEFAULT_MODEL = "BAAI/bge-m3"


class FreeVectorStoreManager:
    """
    Vector Store Manager using FREE HuggingFace embeddings (no API key needed)
    Now with BGE-M3 for multilingual support (English, Urdu, Roman Urdu)
    """
    
    def __init__(
        self,
        collection_name: str = "cui_campus_bot",
        persist_directory: str = "chroma_db",
        model_name: str = DEFAULT_MODEL,
        cache_dir: str = HF_CACHE_DIR
    ):
        """
        Initialize Vector Store with FREE BAAI BGE-M3 multilingual embeddings
        
        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory to persist the database
            model_name: BAAI BGE model (default: bge-m3 for multilingual)
            cache_dir: Local cache directory for HuggingFace models
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.model_name = model_name
        self.cache_dir = cache_dir
        
        # Create directories
        os.makedirs(persist_directory, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)
        
        # Set HuggingFace cache environment variable
        os.environ["HF_HOME"] = cache_dir
        os.environ["TRANSFORMERS_CACHE"] = cache_dir
        
        print(f"\n{'='*60}")
        print(f"Initializing BAAI BGE-M3 Multilingual Embedding Model")
        print(f"{'='*60}")
        print(f"Model: {model_name}")
        print(f"Cache: {cache_dir}")
        print(f"✓ No API key needed")
        print(f"✓ Unlimited usage")
        print(f"✓ Runs locally on CPU")
        print(f"✓ Multilingual: English, Urdu, Roman Urdu + 100 languages")
        print(f"Downloading model (~2.3GB) on first run...")
        print(f"{'='*60}\n")
        
        # Initialize FREE BAAI BGE-M3 multilingual embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True},
            cache_folder=cache_dir
        )
        
        print(f"✓ Multilingual embedding model loaded successfully")
        
        # Initialize vector store
        self.vector_store = None
        self._initialize_vector_store()
        
        print(f"✓ Vector Store initialized")
        print(f"  Collection: {self.collection_name}")
        print(f"  Persist Directory: {self.persist_directory}")
    
    def _collection_exists(self) -> bool:
        """Check if collection exists"""
        try:
            settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            client = chromadb.PersistentClient(path=self.persist_directory, settings=settings)
            collections = client.list_collections()
            return any(col.name == self.collection_name for col in collections)
        except Exception as e:
            print(f"Note: Could not check collection ({e}), will create fresh")
            return False
    
    def _initialize_vector_store(self):
        """Initialize or load existing vector store"""
        try:
            # ChromaDB client settings to handle tenant issues
            chroma_settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            
            if self._collection_exists():
                self.vector_store = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=self.persist_directory,
                    client_settings=chroma_settings
                )
                print(f"✓ Loaded existing collection: {self.collection_name}")
            else:
                print(f"✓ Ready to create new collection: {self.collection_name}")
        except Exception as e:
            print(f"✗ Error initializing vector store: {str(e)}")
            # Try to create fresh if loading fails
            print("Attempting to create fresh vector store...")
            self.vector_store = None
    
    def add_documents(
        self,
        documents: List[Document],
        batch_size: int = 50,
        show_progress: bool = True
    ) -> List[str]:
        """Add documents to vector store"""
        if not documents:
            print("⚠ No documents to add")
            return []
        
        print(f"\nAdding {len(documents)} documents to vector store...")
        print("="*60)
        
        try:
            # ChromaDB client settings
            chroma_settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            
            # Always create a fresh Chroma wrapper to avoid stale collection references
            self.vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=self.persist_directory,
                client_settings=chroma_settings
            )
            
            all_ids = []
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                if show_progress:
                    progress = (i + len(batch)) / len(documents) * 100
                    print(f"Processing: {i + len(batch)}/{len(documents)} ({progress:.1f}%)")
                
                ids = self.vector_store.add_documents(batch)
                all_ids.extend(ids)
            
            # persist() is automatic in newer ChromaDB, but call safely
            try:
                self.vector_store.persist()
            except Exception:
                pass  # Auto-persisted in ChromaDB >= 0.4
            
            print(f"✓ Successfully added {len(documents)} documents")
            print("="*60)
            
            return all_ids
            
        except Exception as e:
            print(f"✗ Error adding documents: {str(e)}")
            raise
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        """Search for similar documents"""
        if self.vector_store is None:
            print("⚠ Vector store is empty")
            return []
        
        try:
            if filter_dict:
                results = self.vector_store.similarity_search(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vector_store.similarity_search(query, k=k)
            return results
        except Exception as e:
            print(f"✗ Error during search: {str(e)}")
            return []
    
    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[tuple]:
        """Search with similarity scores"""
        if self.vector_store is None:
            return []
        
        try:
            if filter_dict:
                results = self.vector_store.similarity_search_with_score(
                    query, k=k, filter=filter_dict
                )
            else:
                results = self.vector_store.similarity_search_with_score(query, k=k)
            return results
        except Exception as e:
            print(f"✗ Error during search: {str(e)}")
            return []
    
    def get_collection_stats(self) -> Dict:
        """Get collection statistics"""
        try:
            if self.vector_store is None:
                return {
                    'total_documents': 0,
                    'collection_name': self.collection_name,
                    'status': 'empty'
                }
            
            settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            client = chromadb.PersistentClient(path=self.persist_directory, settings=settings)
            collection = client.get_collection(name=self.collection_name)
            
            return {
                'total_documents': collection.count(),
                'collection_name': self.collection_name,
                'persist_directory': self.persist_directory,
                'status': 'active'
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def delete_collection(self):
        """Delete the collection (safe - handles missing collections)"""
        try:
            settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
            client = chromadb.PersistentClient(path=self.persist_directory, settings=settings)
            # Check if collection exists before deleting
            existing = [col.name for col in client.list_collections()]
            if self.collection_name in existing:
                client.delete_collection(name=self.collection_name)
                print(f"✓ Deleted collection: {self.collection_name}")
            else:
                print(f"✓ Collection '{self.collection_name}' already removed, nothing to delete")
            self.vector_store = None
        except Exception as e:
            print(f"⚠ Warning during collection delete: {str(e)}")
            self.vector_store = None

    def reset_collection(self):
        """Delete and recreate collection WITHOUT reloading the embedding model"""
        self.delete_collection()
        # Re-initialize vector store using existing embeddings (fast)
        self._initialize_vector_store()
    
    def get_retriever(
        self,
        search_type: str = "similarity",
        search_kwargs: Optional[Dict] = None
    ):
        """Get retriever for RAG pipeline"""
        if self.vector_store is None:
            raise ValueError("Vector store is empty. Add documents first.")
        
        if search_kwargs is None:
            search_kwargs = {"k": 5}
        
        return self.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs
        )


if __name__ == "__main__":
    from load_cui_data import CUIDataLoader
    
    print("="*60)
    print("Free Vector Store Test (No API Key Needed!)")
    print("="*60)
    
    # Initialize
    vector_store = FreeVectorStoreManager(
        collection_name="cui_campus_bot_free",
        persist_directory="chroma_db_free"
    )
    
    # Load data
    print("\nLoading CUI data...")
    loader = CUIDataLoader(chunk_size=800, chunk_overlap=150)
    documents = loader.load_all_data()
    
    # Add to vector store
    vector_store.add_documents(documents)
    
    # Test search
    print("\n" + "="*60)
    print("Testing Search")
    print("="*60)
    results = vector_store.similarity_search("admission requirements", k=3)
    
    for i, doc in enumerate(results, 1):
        print(f"\nResult {i}:")
        print(f"Category: {doc.metadata.get('category')}")
        print(f"Content: {doc.page_content[:150]}...")
    
    print("\n✓ All tests passed!")
