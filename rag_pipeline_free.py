"""
FREE RAG Pipeline - No API quotas, unlimited usage
Uses BAAI BGE embeddings (local) + Groq/Perplexity LLM (API)
"""

import os
from typing import List, Dict, Optional
from langchain_core.documents import Document
from load_cui_data import CUIDataLoader
from vector_store_free import FreeVectorStoreManager
from config import LLM_PROVIDER, PPLX_MODEL, PPLX_TEMPERATURE
from perplexity_llm import PerplexityLLM
from groq_llm import GroqLLM


class FreeRAGPipeline:
    """
    Free RAG Pipeline using local embeddings
    No embedding API quotas - uses Perplexity for text generation
    """
    
    def __init__(
        self,
        data_directory: str = "cui_chatbot_data",
        vector_store_collection: str = "cui_campus_bot",
        vector_store_directory: str = "chroma_db",
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        top_k: int = 5,
        search_type: str = "similarity"
    ):
        """Initialize FREE RAG Pipeline"""
        self.data_directory = data_directory
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.search_type = search_type
        
        self.data_loader = None
        self.vector_store = None
        self.llm = None
        self.retriever = None
        
        self._initialize_components(vector_store_collection, vector_store_directory)
        
        print(f"\n{'='*60}")
        print(f"FREE RAG Pipeline Initialized Successfully")
        print(f"{'='*60}")
        print(f"Embeddings: BAAI BGE (local, unlimited)")
        active_llm = 'Groq' if LLM_PROVIDER == 'groq' else 'Perplexity'
        print(f"LLM: {active_llm} (provider: {LLM_PROVIDER})")
        print(f"Data Directory: {data_directory}")
        print(f"Vector Store: {vector_store_collection}")
        print(f"Top-K Retrieval: {top_k}")
        print(f"{'='*60}\n")

    def ensure_retriever(self):
        """Initialize the retriever from existing vector store (no re-indexing).
        Call this on startup when ChromaDB already has saved embeddings."""
        if self.retriever is not None:
            return  # Already initialized
        if self.vector_store and self.vector_store.vector_store is not None:
            self.retriever = self.vector_store.get_retriever(
                search_type=self.search_type,
                search_kwargs={"k": self.top_k}
            )
            print("✓ Retriever initialized from existing ChromaDB embeddings")
        else:
            print("⚠ Cannot initialize retriever — vector store is empty")
    
    def _initialize_components(self, collection_name: str, persist_directory: str):
        """Initialize all pipeline components"""
        print("\nInitializing FREE RAG Pipeline Components...")
        print("-"*60)
        
        # 1. Data Loader
        print("\n[1/3] Initializing Data Loader...")
        self.data_loader = CUIDataLoader(
            data_directory=self.data_directory,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        
        # 2. FREE Vector Store (no API, no quotas!)
        print("\n[2/3] Initializing FREE Vector Store...")
        self.vector_store = FreeVectorStoreManager(
            collection_name=collection_name,
            persist_directory=persist_directory
        )
        
        # 3. LLM Provider: Groq (default) or Perplexity
        print(f"\n[3/3] Initializing LLM (provider: {LLM_PROVIDER})...")
        
        if LLM_PROVIDER == "groq":
            # Use Groq LLM
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            if not api_key:
                raise ValueError("Groq API key missing. Set $env:GROQ_API_KEY or .env before running.")
            from config import GROQ_MODEL, GROQ_TEMPERATURE, GROQ_MAX_TOKENS
            self.llm = GroqLLM(
                api_key=api_key,
                model_name=GROQ_MODEL,
                temperature=GROQ_TEMPERATURE,
                max_tokens=GROQ_MAX_TOKENS
            )
        else:
            # Use Perplexity LLM
            api_key = os.getenv("PPLX_API_KEY", "").strip()
            if not api_key:
                raise ValueError("Perplexity API key missing. Set $env:PPLX_API_KEY or .env before running.")
            self.llm = PerplexityLLM(
                api_key=api_key,
                model_name=PPLX_MODEL,
                temperature=PPLX_TEMPERATURE
            )
    
    def index_data(self, force_reindex: bool = False, mongo_db=None, mongo_gridfs=None) -> int:
        """Index data using FREE embeddings
        
        Args:
            force_reindex: Whether to force reindexing
            mongo_db: MongoDB database connection (optional)
            mongo_gridfs: MongoDB GridFS connection (optional)
        """
        print("\n" + "="*60)
        print("PHASE 1: DATA INDEXING (FREE - No API Quotas!)")
        print("="*60)
        
        # Check if already indexed
        stats = self.vector_store.get_collection_stats()
        if stats.get('total_documents', 0) > 0 and not force_reindex:
            print(f"\n✓ Vector store already contains {stats['total_documents']} documents")
            print("  Use force_reindex=True to rebuild")
            
            # Initialize retriever
            self.retriever = self.vector_store.get_retriever(
                search_type=self.search_type,
                search_kwargs={"k": self.top_k}
            )
            
            return stats['total_documents']
        
        # Load data (from MongoDB if available, else local)
        print("\n[Step 1/3] Data Loading...")
        print("-"*60)
        documents = self.data_loader.load_all_data(mongo_db=mongo_db, mongo_gridfs=mongo_gridfs)
        
        if not documents:
            print("✗ No documents loaded!")
            return 0
        
        # Get stats
        print("\n[Step 2/3] Data Analysis...")
        print("-"*60)
        stats = self.data_loader.get_chunking_stats(documents)
        print(f"✓ Documents split into {len(documents)} chunks")
        print(f"  Average chunk size: {stats['avg_chunk_size']:.0f} characters")
        print(f"  Min/Max: {stats['min_chunk_size']}/{stats['max_chunk_size']} characters")
        
        # Add to vector store (FREE embeddings!)
        print("\n[Step 3/3] Creating FREE Embeddings & Storing...")
        print("-"*60)
        print("Using HuggingFace embeddings (no API calls, unlimited!)")
        
        if force_reindex:
            # Use reset_collection to avoid reloading the 2.3GB embedding model
            self.vector_store.reset_collection()
        
        self.vector_store.add_documents(documents, batch_size=50)
        
        # Initialize retriever
        self.retriever = self.vector_store.get_retriever(
            search_type=self.search_type,
            search_kwargs={"k": self.top_k}
        )
        
        # Final stats
        final_stats = self.vector_store.get_collection_stats()
        
        print("\n" + "="*60)
        print("DATA INDEXING COMPLETE (FREE)")
        print("="*60)
        print(f"Total documents indexed: {final_stats['total_documents']}")
        print(f"Collection: {final_stats['collection_name']}")
        print(f"Status: {final_stats['status']}")
        print("="*60 + "\n")
        
        return final_stats['total_documents']
    
    def retrieve_context(
        self,
        query: str,
        k: Optional[int] = None,
        filter_dict: Optional[Dict] = None,
        return_scores: bool = False
    ) -> List[Document]:
        """Retrieve relevant documents"""
        k = k or self.top_k
        
        if return_scores:
            results = self.vector_store.similarity_search_with_score(
                query, k=k, filter_dict=filter_dict
            )
            return results
        else:
            results = self.vector_store.similarity_search(
                query, k=k, filter_dict=filter_dict
            )
            return results
    
    def generate_response(
        self,
        query: str,
        context_documents: List[Document],
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        language_instruction: Optional[str] = None,
        is_roman_mode: bool = False
    ) -> str:
        """Generate response using Perplexity"""
        if conversation_history:
            response = self.llm.generate_chat_response(
                question=query,
                context_documents=context_documents,
                conversation_history=conversation_history,
                system_prompt=system_prompt,
                language_instruction=language_instruction,
                is_roman_mode=is_roman_mode
            )
        else:
            response = self.llm.generate_response_with_context(
                question=query,
                context_documents=context_documents,
                system_prompt=system_prompt,
                language_instruction=language_instruction,
                is_roman_mode=is_roman_mode
            )
        
        return response
    
    def query(
        self,
        question: str,
        top_k: Optional[int] = None,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        show_context: bool = False,
        return_context: bool = False,
        language_instruction: Optional[str] = None,
        is_roman_mode: bool = False
    ) -> Dict:
        """Complete RAG Query"""
        # Retrieve context
        context_documents = self.retrieve_context(question, k=top_k)
        
        # Show context if requested
        if show_context and context_documents:
            print(f"\n[Context] Retrieved {len(context_documents)} documents")
            for i, doc in enumerate(context_documents, 1):
                print(f"{i}. {doc.metadata.get('category')} - {doc.metadata.get('source')}")
        
        # Generate response - even without context for conversational queries
        # The LLM can handle greetings and general queries naturally
        answer = self.generate_response(
            query=question,
            context_documents=context_documents if context_documents else [],
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            language_instruction=language_instruction,
            is_roman_mode=is_roman_mode
        )
        
        # Prepare result
        result = {
            'answer': answer,
            'sources': list(set([doc.metadata.get('source', 'Unknown') for doc in context_documents])) if context_documents else [],
            'categories': list(set([doc.metadata.get('category', 'Unknown') for doc in context_documents])) if context_documents else [],
            'num_context_docs': len(context_documents) if context_documents else 0
        }
        
        if return_context:
            result['context'] = [doc.page_content for doc in context_documents] if context_documents else []
        
        return result
    
    def get_pipeline_status(self) -> Dict:
        """Get pipeline status"""
        status = {
            'data_loader': 'initialized' if self.data_loader else 'not initialized',
            'vector_store': self.vector_store.get_collection_stats() if self.vector_store else {},
            'llm': 'initialized' if self.llm else 'not initialized',
            'retriever': 'initialized' if self.retriever else 'not initialized',
            'embedding_type': 'HuggingFace (FREE, unlimited)'
        }
        return status


if __name__ == "__main__":
    from config import DATA_DIRECTORY, SYSTEM_PROMPT
    
    print("="*60)
    print("FREE RAG Pipeline Test (Perplexity)")
    print("="*60)
    
    # Initialize
    rag = FreeRAGPipeline(
        data_directory=DATA_DIRECTORY,
        vector_store_collection="cui_campus_bot",
        vector_store_directory="chroma_db",
        chunk_size=800,
        chunk_overlap=150,
        top_k=5
    )
    
    # Index data
    rag.index_data(force_reindex=False)
    
    # Test query
    print("\n" + "="*60)
    print("TEST QUERY")
    print("="*60)
    
    result = rag.query(
        question="What are the admission requirements?",
        system_prompt=SYSTEM_PROMPT,
        show_context=True
    )
    
    print("\nAnswer:")
    print(result['answer'])
    print(f"\nSources: {', '.join(result['sources'])}")
    print(f"Categories: {', '.join(result['categories'])}")
    
    print("\n✓ Test completed successfully!")
