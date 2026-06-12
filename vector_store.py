"""
Vector Store Management using ChromaDB
Handles storing and retrieving document embeddings
"""

import os
import json
from typing import List, Optional, Dict
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import chromadb
from chromadb.config import Settings


class VectorStoreManager:
    """
    Manages vector database operations using ChromaDB
    """
    
    def __init__(
        self,
        collection_name: str = "cui_campus_bot",
        persist_directory: str = "chroma_db",
        embedding_model=None,
        api_key: Optional[str] = None
    ):
        """
        Initialize Vector Store Manager
        
        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory to persist the database
            embedding_model: Embedding model to use (if None, uses Google's)
            api_key: Google API key for embeddings
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.api_key = api_key
        
        # Create persist directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize embedding model
        if embedding_model is None:
            self.embeddings = self._create_embedding_model()
        else:
            self.embeddings = embedding_model
        
        # Initialize vector store
        self.vector_store = None
        self._initialize_vector_store()
        
        print(f"✓ Vector Store initialized")
        print(f"  Collection: {self.collection_name}")
        print(f"  Persist Directory: {self.persist_directory}")
    
    def _create_embedding_model(self):
        """
        Create Google Generative AI Embedding model
        
        Returns:
            GoogleGenerativeAIEmbeddings instance
        """
        try:
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=self.api_key
            )
            print(f"✓ Google Embedding Model initialized")
            return embeddings
        except Exception as e:
            print(f"✗ Error creating embedding model: {str(e)}")
            raise
    
    def _initialize_vector_store(self):
        """
        Initialize or load existing ChromaDB vector store
        """
        try:
            # Check if collection exists
            if self._collection_exists():
                # Load existing collection
                self.vector_store = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=self.persist_directory
                )
                print(f"✓ Loaded existing collection: {self.collection_name}")
            else:
                # Will create new collection when documents are added
                print(f"✓ Ready to create new collection: {self.collection_name}")
                
        except Exception as e:
            print(f"✗ Error initializing vector store: {str(e)}")
            raise
    
    def _collection_exists(self) -> bool:
        """
        Check if collection already exists
        
        Returns:
            True if collection exists, False otherwise
        """
        try:
            client = chromadb.PersistentClient(path=self.persist_directory)
            collections = client.list_collections()
            return any(col.name == self.collection_name for col in collections)
        except:
            return False
    
    def add_documents(
        self,
        documents: List[Document],
        batch_size: int = 100,
        show_progress: bool = True
    ) -> List[str]:
        """
        Add documents to the vector store
        
        Args:
            documents: List of Document objects to add
            batch_size: Number of documents to process at once
            show_progress: Whether to show progress
            
        Returns:
            List of document IDs
        """
        if not documents:
            print("⚠ No documents to add")
            return []
        
        print(f"\nAdding {len(documents)} documents to vector store...")
        print("="*60)
        
        try:
            # Create vector store if it doesn't exist
            if self.vector_store is None:
                self.vector_store = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=self.persist_directory
                )
            
            # Add documents in batches
            all_ids = []
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                if show_progress:
                    print(f"Processing batch {i//batch_size + 1}/{(len(documents)-1)//batch_size + 1}...")
                
                # Add batch to vector store
                ids = self.vector_store.add_documents(batch)
                all_ids.extend(ids)
            
            # Persist the changes
            self.vector_store.persist()
            
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
        """
        Search for similar documents
        
        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Metadata filter (e.g., {'category': 'Admission'})
            
        Returns:
            List of similar Document objects
        """
        if self.vector_store is None:
            print("⚠ Vector store is empty")
            return []
        
        try:
            if filter_dict:
                results = self.vector_store.similarity_search(
                    query,
                    k=k,
                    filter=filter_dict
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
        """
        Search for similar documents with similarity scores
        
        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Metadata filter
            
        Returns:
            List of tuples (Document, score)
        """
        if self.vector_store is None:
            print("⚠ Vector store is empty")
            return []
        
        try:
            if filter_dict:
                results = self.vector_store.similarity_search_with_score(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = self.vector_store.similarity_search_with_score(query, k=k)
            
            return results
            
        except Exception as e:
            print(f"✗ Error during search: {str(e)}")
            return []
    
    def max_marginal_relevance_search(
        self,
        query: str,
        k: int = 5,
        fetch_k: int = 20,
        lambda_mult: float = 0.5
    ) -> List[Document]:
        """
        Search using Maximum Marginal Relevance (MMR)
        Balances relevance and diversity
        
        Args:
            query: Search query
            k: Number of results to return
            fetch_k: Number of documents to fetch initially
            lambda_mult: Diversity factor (0=max diversity, 1=max relevance)
            
        Returns:
            List of Document objects
        """
        if self.vector_store is None:
            print("⚠ Vector store is empty")
            return []
        
        try:
            results = self.vector_store.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=fetch_k,
                lambda_mult=lambda_mult
            )
            return results
            
        except Exception as e:
            print(f"✗ Error during MMR search: {str(e)}")
            return []
    
    def get_collection_stats(self) -> Dict:
        """
        Get statistics about the vector store collection
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            if self.vector_store is None:
                return {
                    'total_documents': 0,
                    'collection_name': self.collection_name,
                    'status': 'empty'
                }
            
            # Get collection
            client = chromadb.PersistentClient(path=self.persist_directory)
            collection = client.get_collection(name=self.collection_name)
            
            stats = {
                'total_documents': collection.count(),
                'collection_name': self.collection_name,
                'persist_directory': self.persist_directory,
                'status': 'active'
            }
            
            return stats
            
        except Exception as e:
            print(f"✗ Error getting stats: {str(e)}")
            return {'status': 'error', 'error': str(e)}
    
    def delete_collection(self):
        """
        Delete the entire collection
        """
        try:
            client = chromadb.PersistentClient(path=self.persist_directory)
            client.delete_collection(name=self.collection_name)
            self.vector_store = None
            print(f"✓ Deleted collection: {self.collection_name}")
            
        except Exception as e:
            print(f"✗ Error deleting collection: {str(e)}")
    
    def update_documents(
        self,
        documents: List[Document],
        delete_old: bool = True
    ):
        """
        Update the vector store with new documents
        
        Args:
            documents: New documents to add
            delete_old: Whether to delete old collection first
        """
        if delete_old and self._collection_exists():
            print("Deleting old collection...")
            self.delete_collection()
            self._initialize_vector_store()
        
        return self.add_documents(documents)
    
    def get_retriever(
        self,
        search_type: str = "similarity",
        search_kwargs: Optional[Dict] = None
    ):
        """
        Get a retriever for RAG pipeline
        
        Args:
            search_type: Type of search ('similarity', 'mmr', 'similarity_score_threshold')
            search_kwargs: Additional search parameters
            
        Returns:
            VectorStoreRetriever instance
        """
        if self.vector_store is None:
            raise ValueError("Vector store is empty. Add documents first.")
        
        if search_kwargs is None:
            search_kwargs = {"k": 5}
        
        retriever = self.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs
        )
        
        return retriever
    
    def save_metadata(self, filepath: str = "vector_store_metadata.json"):
        """
        Save metadata about the vector store
        
        Args:
            filepath: Path to save metadata file
        """
        stats = self.get_collection_stats()
        metadata = {
            'collection_name': self.collection_name,
            'persist_directory': self.persist_directory,
            'total_documents': stats.get('total_documents', 0),
            'embedding_model': 'models/embedding-001'
        }
        
        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✓ Metadata saved to {filepath}")


# Example usage and testing
if __name__ == "__main__":
    from config import GOOGLE_API_KEY, CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIRECTORY
    from load_cui_data import CUIDataLoader
    
    print("="*60)
    print("Vector Store Test")
    print("="*60)
    
    try:
        # Initialize vector store
        vector_store_manager = VectorStoreManager(
            collection_name=CHROMA_COLLECTION_NAME,
            persist_directory=CHROMA_PERSIST_DIRECTORY,
            api_key=GOOGLE_API_KEY
        )
        
        # Load CUI data
        print("\nLoading CUI data...")
        data_loader = CUIDataLoader(
            data_directory="cui_chatbot_data",
            chunk_size=800,
            chunk_overlap=150
        )
        documents = data_loader.load_all_data()
        
        # Add documents to vector store
        print("\nAdding documents to vector store...")
        ids = vector_store_manager.add_documents(documents, batch_size=50)
        
        # Get collection stats
        print("\nCollection Statistics:")
        stats = vector_store_manager.get_collection_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Test similarity search
        print("\n" + "="*60)
        print("Testing Similarity Search")
        print("="*60)
        
        query = "What are the admission requirements?"
        print(f"\nQuery: {query}")
        print("-"*60)
        
        results = vector_store_manager.similarity_search(query, k=3)
        
        for i, doc in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(f"Category: {doc.metadata.get('category')}")
            print(f"Source: {doc.metadata.get('source')}")
            print(f"Content: {doc.page_content[:200]}...")
        
        # Test search with scores
        print("\n" + "="*60)
        print("Testing Search with Scores")
        print("="*60)
        
        results_with_scores = vector_store_manager.similarity_search_with_score(query, k=3)
        
        for i, (doc, score) in enumerate(results_with_scores, 1):
            print(f"\nResult {i} (Score: {score:.4f}):")
            print(f"Category: {doc.metadata.get('category')}")
            print(f"Content: {doc.page_content[:150]}...")
        
        # Test MMR search
        print("\n" + "="*60)
        print("Testing MMR Search (Diversity)")
        print("="*60)
        
        mmr_results = vector_store_manager.max_marginal_relevance_search(
            query,
            k=3,
            lambda_mult=0.5
        )
        
        for i, doc in enumerate(mmr_results, 1):
            print(f"\nResult {i}:")
            print(f"Category: {doc.metadata.get('category')}")
            print(f"Content: {doc.page_content[:150]}...")
        
        # Save metadata
        vector_store_manager.save_metadata()
        
        print("\n" + "="*60)
        print("✓ All tests completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()
