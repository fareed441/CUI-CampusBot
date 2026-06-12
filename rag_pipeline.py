"""
RAG (Retrieval-Augmented Generation) Pipeline
Complete implementation following the Basic RAG Pipeline architecture
"""

import os
from typing import List, Dict, Optional, Tuple
from langchain_core.documents import Document
from load_cui_data import CUIDataLoader
from vector_store import VectorStoreManager
from gemini_llm import GeminiLLM


class RAGPipeline:
    """
    Complete RAG Pipeline for CUI Campus Chatbot
    
    Architecture:
    1. Data Indexing:
       - Data Loading → Data Splitting → Data Embedding → Data Storing (Vector DB)
    
    2. Data Retrieval & Generation:
       - User Query → Vector Embedding → Retrieval (Top-K Chunks) → LLM → Response
    """
    
    def __init__(
        self,
        api_key: str,
        data_directory: str = "cui_chatbot_data",
        vector_store_collection: str = "cui_campus_bot",
        vector_store_directory: str = "chroma_db",
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        top_k: int = 5,
        search_type: str = "similarity"
    ):
        """
        Initialize RAG Pipeline
        
        Args:
            api_key: Google API key
            data_directory: Directory containing CUI data
            vector_store_collection: ChromaDB collection name
            vector_store_directory: Directory to store vector database
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
            top_k: Number of documents to retrieve
            search_type: Type of search ('similarity', 'mmr')
        """
        self.api_key = api_key
        self.data_directory = data_directory
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.search_type = search_type
        
        # Components
        self.data_loader = None
        self.vector_store = None
        self.llm = None
        self.retriever = None
        
        # Initialize components
        self._initialize_components(vector_store_collection, vector_store_directory)
        
        print(f"\n{'='*60}")
        print(f"RAG Pipeline Initialized Successfully")
        print(f"{'='*60}")
        print(f"Data Directory: {data_directory}")
        print(f"Vector Store: {vector_store_collection}")
        print(f"Top-K Retrieval: {top_k}")
        print(f"Search Type: {search_type}")
        print(f"{'='*60}\n")
    
    def _initialize_components(self, collection_name: str, persist_directory: str):
        """
        Initialize all pipeline components
        
        Args:
            collection_name: Vector store collection name
            persist_directory: Vector store persist directory
        """
        print("\nInitializing RAG Pipeline Components...")
        print("-"*60)
        
        # 1. Initialize Data Loader
        print("\n[1/3] Initializing Data Loader...")
        self.data_loader = CUIDataLoader(
            data_directory=self.data_directory,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        
        # 2. Initialize Vector Store
        print("\n[2/3] Initializing Vector Store...")
        self.vector_store = VectorStoreManager(
            collection_name=collection_name,
            persist_directory=persist_directory,
            api_key=self.api_key
        )
        
        # 3. Initialize LLM
        print("\n[3/3] Initializing Gemini LLM...")
        self.llm = GeminiLLM(
            api_key=self.api_key,
            model_name="gemini-1.5-flash",
            temperature=0.7
        )
    
    def index_data(self, force_reindex: bool = False) -> int:
        """
        PHASE 1: DATA INDEXING
        Load, split, embed, and store documents in vector database
        
        Args:
            force_reindex: Whether to delete existing index and recreate
            
        Returns:
            Number of documents indexed
        """
        print("\n" + "="*60)
        print("PHASE 1: DATA INDEXING")
        print("="*60)
        
        # Check if already indexed
        stats = self.vector_store.get_collection_stats()
        if stats.get('total_documents', 0) > 0 and not force_reindex:
            print(f"\n✓ Vector store already contains {stats['total_documents']} documents")
            print("  Use force_reindex=True to rebuild the index")
            return stats['total_documents']
        
        # Step 1: Data Loading
        print("\n[Step 1/4] Data Loading...")
        print("-"*60)
        documents = self.data_loader.load_all_data()
        
        if not documents:
            print("✗ No documents loaded!")
            return 0
        
        # Step 2: Data Splitting (already done in data loader)
        print("\n[Step 2/4] Data Splitting...")
        print("-"*60)
        print(f"✓ Documents split into {len(documents)} chunks")
        
        # Get chunking stats
        stats = self.data_loader.get_chunking_stats(documents)
        print(f"  Average chunk size: {stats['avg_chunk_size']:.0f} characters")
        print(f"  Min/Max: {stats['min_chunk_size']}/{stats['max_chunk_size']} characters")
        
        # Step 3 & 4: Data Embedding & Storing
        print("\n[Step 3-4/4] Data Embedding & Storing in Vector DB...")
        print("-"*60)
        
        if force_reindex:
            self.vector_store.update_documents(documents, delete_old=True)
        else:
            self.vector_store.add_documents(documents, batch_size=50)
        
        # Initialize retriever
        self.retriever = self.vector_store.get_retriever(
            search_type=self.search_type,
            search_kwargs={"k": self.top_k}
        )
        
        # Final stats
        final_stats = self.vector_store.get_collection_stats()
        
        print("\n" + "="*60)
        print("DATA INDEXING COMPLETE")
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
        """
        PHASE 2 (Part 1): DATA RETRIEVAL
        Retrieve relevant documents for a query
        
        Args:
            query: User's question
            k: Number of documents to retrieve (uses default if None)
            filter_dict: Metadata filter
            return_scores: Whether to return similarity scores
            
        Returns:
            List of relevant Document objects or tuples (Document, score)
        """
        k = k or self.top_k
        
        print(f"\n[Retrieval] Searching for top-{k} relevant documents...")
        
        if return_scores:
            results = self.vector_store.similarity_search_with_score(
                query,
                k=k,
                filter_dict=filter_dict
            )
            
            print(f"✓ Retrieved {len(results)} documents with scores")
            for i, (doc, score) in enumerate(results, 1):
                category = doc.metadata.get('category', 'Unknown')
                print(f"  {i}. {category} (Score: {score:.4f})")
            
            return results
        else:
            results = self.vector_store.similarity_search(
                query,
                k=k,
                filter_dict=filter_dict
            )
            
            print(f"✓ Retrieved {len(results)} documents")
            for i, doc in enumerate(results, 1):
                category = doc.metadata.get('category', 'Unknown')
                source = doc.metadata.get('source', 'Unknown')
                print(f"  {i}. {category} - {source}")
            
            return results
    
    def generate_response(
        self,
        query: str,
        context_documents: List[Document],
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None
    ) -> str:
        """
        PHASE 2 (Part 2): RESPONSE GENERATION
        Generate response using LLM with retrieved context
        
        Args:
            query: User's question
            context_documents: Retrieved relevant documents
            system_prompt: Optional system prompt
            conversation_history: Previous conversation turns
            
        Returns:
            Generated response
        """
        print(f"\n[Generation] Generating response using Gemini LLM...")
        
        if conversation_history:
            response = self.llm.generate_chat_response(
                question=query,
                context_documents=context_documents,
                conversation_history=conversation_history,
                system_prompt=system_prompt
            )
        else:
            response = self.llm.generate_response_with_context(
                question=query,
                context_documents=context_documents,
                system_prompt=system_prompt
            )
        
        print(f"✓ Response generated successfully")
        
        return response
    
    def query(
        self,
        question: str,
        top_k: Optional[int] = None,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        show_context: bool = False,
        return_context: bool = False
    ) -> Dict:
        """
        Complete RAG Query: Retrieve + Generate
        
        Args:
            question: User's question
            top_k: Number of documents to retrieve
            system_prompt: Optional system prompt
            conversation_history: Previous conversation
            show_context: Whether to display retrieved context
            return_context: Whether to include context in response
            
        Returns:
            Dictionary with answer and metadata
        """
        print("\n" + "="*60)
        print("PHASE 2: DATA RETRIEVAL & GENERATION")
        print("="*60)
        print(f"Query: {question}")
        print("-"*60)
        
        # Step 1: Vector Embedding & Retrieval
        context_documents = self.retrieve_context(question, k=top_k)
        
        if not context_documents:
            return {
                'answer': "I couldn't find relevant information to answer your question.",
                'context': [],
                'sources': []
            }
        
        # Show context if requested
        if show_context:
            print(f"\n[Context] Retrieved Documents:")
            print("-"*60)
            for i, doc in enumerate(context_documents, 1):
                print(f"\n{i}. {doc.metadata.get('category')} - {doc.metadata.get('source')}")
                print(f"   {doc.page_content[:200]}...")
        
        # Step 2: LLM Generation
        answer = self.generate_response(
            query=question,
            context_documents=context_documents,
            system_prompt=system_prompt,
            conversation_history=conversation_history
        )
        
        # Prepare result
        result = {
            'answer': answer,
            'sources': list(set([doc.metadata.get('source', 'Unknown') for doc in context_documents])),
            'categories': list(set([doc.metadata.get('category', 'Unknown') for doc in context_documents])),
            'num_context_docs': len(context_documents)
        }
        
        if return_context:
            result['context'] = [doc.page_content for doc in context_documents]
        
        print("\n" + "="*60)
        print("RESPONSE GENERATED")
        print("="*60)
        
        return result
    
    def interactive_chat(self, system_prompt: Optional[str] = None):
        """
        Interactive chat session with conversation history
        
        Args:
            system_prompt: Optional system prompt for chatbot behavior
        """
        print("\n" + "="*60)
        print("CUI Campus Chatbot - Interactive Mode")
        print("="*60)
        print("Type 'quit', 'exit', or 'q' to end the conversation")
        print("Type 'clear' to clear conversation history")
        print("="*60 + "\n")
        
        conversation_history = []
        
        while True:
            try:
                # Get user input
                user_input = input("\nYou: ").strip()
                
                if not user_input:
                    continue
                
                # Check for exit commands
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nGoodbye! 👋")
                    break
                
                # Check for clear command
                if user_input.lower() == 'clear':
                    conversation_history = []
                    print("\n✓ Conversation history cleared")
                    continue
                
                # Get response
                result = self.query(
                    question=user_input,
                    system_prompt=system_prompt,
                    conversation_history=conversation_history,
                    show_context=False
                )
                
                # Display response
                print(f"\nBot: {result['answer']}")
                print(f"\n📚 Sources: {', '.join(result['sources'])}")
                print(f"📑 Categories: {', '.join(result['categories'])}")
                
                # Update conversation history
                conversation_history.append({
                    'question': user_input,
                    'answer': result['answer']
                })
                
                # Keep last 10 turns
                if len(conversation_history) > 10:
                    conversation_history = conversation_history[-10:]
                
            except KeyboardInterrupt:
                print("\n\nGoodbye! 👋")
                break
            except Exception as e:
                print(f"\n✗ Error: {str(e)}")
    
    def get_pipeline_status(self) -> Dict:
        """
        Get status of all pipeline components
        
        Returns:
            Dictionary with component status
        """
        status = {
            'data_loader': 'initialized' if self.data_loader else 'not initialized',
            'vector_store': self.vector_store.get_collection_stats() if self.vector_store else {},
            'llm': 'initialized' if self.llm else 'not initialized',
            'retriever': 'initialized' if self.retriever else 'not initialized'
        }
        
        return status


# Example usage and testing
if __name__ == "__main__":
    from config import (
        GOOGLE_API_KEY,
        DATA_DIRECTORY,
        CHROMA_COLLECTION_NAME,
        CHROMA_PERSIST_DIRECTORY,
        CHUNK_SIZE,
        CHUNK_OVERLAP,
        RETRIEVAL_TOP_K,
        SYSTEM_PROMPT
    )
    
    print("="*60)
    print("RAG Pipeline Test")
    print("="*60)
    
    try:
        # Initialize RAG Pipeline
        rag = RAGPipeline(
            api_key=GOOGLE_API_KEY,
            data_directory=DATA_DIRECTORY,
            vector_store_collection=CHROMA_COLLECTION_NAME,
            vector_store_directory=CHROMA_PERSIST_DIRECTORY,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            top_k=RETRIEVAL_TOP_K
        )
        
        # Index data (only if not already indexed)
        rag.index_data(force_reindex=False)
        
        # Test queries
        test_questions = [
            "What are the admission requirements for undergraduate programs?",
            "How many campuses does COMSATS University have?",
            "What scholarships are available?",
            "When do the classes start?"
        ]
        
        print("\n" + "="*60)
        print("TESTING RAG PIPELINE WITH SAMPLE QUERIES")
        print("="*60)
        
        for i, question in enumerate(test_questions, 1):
            print(f"\n\n{'='*60}")
            print(f"TEST QUERY {i}/{len(test_questions)}")
            print(f"{'='*60}")
            
            result = rag.query(
                question=question,
                system_prompt=SYSTEM_PROMPT,
                show_context=True
            )
            
            print(f"\n💬 Answer:")
            print(result['answer'])
            print(f"\n📚 Sources: {', '.join(result['sources'])}")
            print(f"📑 Categories: {', '.join(result['categories'])}")
        
        # Get pipeline status
        print("\n\n" + "="*60)
        print("PIPELINE STATUS")
        print("="*60)
        status = rag.get_pipeline_status()
        for component, info in status.items():
            print(f"{component}: {info}")
        
        print("\n" + "="*60)
        print("✓ All tests completed successfully!")
        print("="*60)
        
        # Optional: Start interactive chat
        print("\n\nWould you like to start an interactive chat? (y/n): ", end="")
        choice = input().strip().lower()
        if choice == 'y':
            rag.interactive_chat(system_prompt=SYSTEM_PROMPT)
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
