"""
Google Vertex AI Embedding Model Integration
Handles text embeddings using Google's Embedding Model via Vertex AI
"""

import os
from typing import List, Optional
from google.cloud import aiplatform
from google.oauth2 import service_account
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_core.documents import Document
import numpy as np


class GoogleEmbeddingModel:
    """
    Google Vertex AI Embedding Model for generating text embeddings
    """
    
    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model_name: str = "textembedding-gecko@003",
        credentials_path: Optional[str] = None
    ):
        """
        Initialize Google Vertex AI Embedding Model
        
        Args:
            project_id: Google Cloud Project ID
            location: GCP region (default: us-central1)
            model_name: Embedding model name
            credentials_path: Path to service account JSON file
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.credentials_path = credentials_path
        
        # Initialize Vertex AI
        self._initialize_vertex_ai()
        
        # Initialize embedding model
        self.embeddings = self._create_embedding_model()
    
    def _initialize_vertex_ai(self):
        """
        Initialize Vertex AI with credentials
        """
        try:
            if self.credentials_path and os.path.exists(self.credentials_path):
                # Use service account credentials
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                aiplatform.init(
                    project=self.project_id,
                    location=self.location,
                    credentials=credentials
                )
                print(f"✓ Initialized Vertex AI with service account")
            else:
                # Use default credentials (for local gcloud auth or cloud environment)
                aiplatform.init(
                    project=self.project_id,
                    location=self.location
                )
                print(f"✓ Initialized Vertex AI with default credentials")
            
            print(f"  Project: {self.project_id}")
            print(f"  Location: {self.location}")
            print(f"  Model: {self.model_name}")
            
        except Exception as e:
            print(f"✗ Error initializing Vertex AI: {str(e)}")
            raise
    
    def _create_embedding_model(self) -> VertexAIEmbeddings:
        """
        Create Langchain VertexAI Embeddings instance
        
        Returns:
            VertexAIEmbeddings object
        """
        try:
            embeddings = VertexAIEmbeddings(
                model_name=self.model_name,
                project=self.project_id,
                location=self.location
            )
            print(f"✓ Embedding model initialized successfully")
            return embeddings
        except Exception as e:
            print(f"✗ Error creating embedding model: {str(e)}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            embedding = self.embeddings.embed_query(text)
            return embedding
        except Exception as e:
            print(f"Error embedding text: {str(e)}")
            return []
    
    def embed_texts(self, texts: List[str], batch_size: int = 5) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process per batch
            
        Returns:
            List of embedding vectors
        """
        try:
            # Process in batches to avoid API limits
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_embeddings = self.embeddings.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)
                
                if (i + batch_size) % 20 == 0:
                    print(f"  Processed {min(i + batch_size, len(texts))}/{len(texts)} texts")
            
            print(f"✓ Generated embeddings for {len(texts)} texts")
            return all_embeddings
            
        except Exception as e:
            print(f"✗ Error embedding texts: {str(e)}")
            return []
    
    def embed_documents(
        self,
        documents: List[Document],
        batch_size: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for Langchain Document objects
        
        Args:
            documents: List of Document objects
            batch_size: Number of documents to process per batch
            
        Returns:
            List of embedding vectors
        """
        texts = [doc.page_content for doc in documents]
        return self.embed_texts(texts, batch_size=batch_size)
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of the embedding vectors
        
        Returns:
            Integer dimension of embeddings
        """
        # textembedding-gecko models return 768-dimensional vectors
        if "gecko" in self.model_name.lower():
            return 768
        # For other models, generate a sample embedding
        sample_embedding = self.embed_text("test")
        return len(sample_embedding)
    
    def calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Cosine similarity
        similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        return float(similarity)


class EmbeddingManager:
    """
    Manages embeddings for documents with caching and batch processing
    """
    
    def __init__(self, embedding_model: GoogleEmbeddingModel):
        """
        Initialize embedding manager
        
        Args:
            embedding_model: GoogleEmbeddingModel instance
        """
        self.embedding_model = embedding_model
        self.embedding_cache = {}
    
    def create_embeddings_for_documents(
        self,
        documents: List[Document],
        use_cache: bool = True,
        batch_size: int = 5
    ) -> List[List[float]]:
        """
        Create embeddings for documents with optional caching
        
        Args:
            documents: List of Document objects
            use_cache: Whether to use cached embeddings
            batch_size: Batch size for processing
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        documents_to_embed = []
        indices_to_embed = []
        
        print(f"\nGenerating embeddings for {len(documents)} documents...")
        print("="*60)
        
        # Check cache
        for i, doc in enumerate(documents):
            cache_key = hash(doc.page_content)
            
            if use_cache and cache_key in self.embedding_cache:
                embeddings.append(self.embedding_cache[cache_key])
            else:
                embeddings.append(None)
                documents_to_embed.append(doc)
                indices_to_embed.append(i)
        
        # Generate embeddings for non-cached documents
        if documents_to_embed:
            print(f"Creating {len(documents_to_embed)} new embeddings...")
            new_embeddings = self.embedding_model.embed_documents(
                documents_to_embed,
                batch_size=batch_size
            )
            
            # Update results and cache
            for idx, embedding in zip(indices_to_embed, new_embeddings):
                embeddings[idx] = embedding
                if use_cache:
                    cache_key = hash(documents[idx].page_content)
                    self.embedding_cache[cache_key] = embedding
            
            print(f"✓ Created {len(new_embeddings)} new embeddings")
        
        if use_cache:
            print(f"✓ Used {len(documents) - len(documents_to_embed)} cached embeddings")
        
        print("="*60)
        return embeddings
    
    def get_cache_stats(self) -> dict:
        """
        Get statistics about the embedding cache
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'cached_embeddings': len(self.embedding_cache),
            'cache_size_mb': sum(
                len(emb) * 4 for emb in self.embedding_cache.values()
            ) / (1024 * 1024)  # Approximate size in MB
        }


# Example usage and testing
if __name__ == "__main__":
    # Configuration
    PROJECT_ID = "your-google-cloud-project-id"
    LOCATION = "us-central1"
    CREDENTIALS_PATH = "path/to/service-account-key.json"  # Optional
    
    print("="*60)
    print("Google Vertex AI Embedding Model Test")
    print("="*60)
    
    try:
        # Initialize embedding model
        embedding_model = GoogleEmbeddingModel(
            project_id=PROJECT_ID,
            location=LOCATION,
            model_name="textembedding-gecko@003",
            credentials_path=CREDENTIALS_PATH if os.path.exists(CREDENTIALS_PATH) else None
        )
        
        # Test single text embedding
        print("\n1. Testing single text embedding:")
        sample_text = "What are the admission requirements for COMSATS University?"
        embedding = embedding_model.embed_text(sample_text)
        print(f"   Text: {sample_text}")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        
        # Test multiple texts
        print("\n2. Testing batch text embedding:")
        sample_texts = [
            "How do I apply for scholarships?",
            "What is the fee structure?",
            "When do classes start?"
        ]
        embeddings = embedding_model.embed_texts(sample_texts)
        print(f"   Generated {len(embeddings)} embeddings")
        
        # Test similarity calculation
        print("\n3. Testing similarity calculation:")
        text1 = "admission process"
        text2 = "how to apply"
        text3 = "campus facilities"
        
        emb1 = embedding_model.embed_text(text1)
        emb2 = embedding_model.embed_text(text2)
        emb3 = embedding_model.embed_text(text3)
        
        sim_12 = embedding_model.calculate_similarity(emb1, emb2)
        sim_13 = embedding_model.calculate_similarity(emb1, emb3)
        
        print(f"   Similarity ('{text1}' vs '{text2}'): {sim_12:.4f}")
        print(f"   Similarity ('{text1}' vs '{text3}'): {sim_13:.4f}")
        
        print("\n" + "="*60)
        print("✓ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error during testing: {str(e)}")
        print("\nMake sure to:")
        print("1. Set up Google Cloud Project")
        print("2. Enable Vertex AI API")
        print("3. Configure authentication (service account or gcloud)")
        print("4. Update PROJECT_ID in the code")
