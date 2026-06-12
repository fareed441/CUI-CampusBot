"""
FREE LLM using HuggingFace Transformers (local, no API)
Alternative to Gemini when quota is exceeded
"""

from transformers import pipeline
from typing import List, Optional
from langchain_core.documents import Document


class FreeLLM:
    """
    FREE Local LLM using HuggingFace Transformers
    No API key required, no quotas
    """
    
    def __init__(
        self,
        model_name: str = "google/flan-t5-base",
        max_length: int = 512,
        temperature: float = 0.7
    ):
        """
        Initialize FREE LLM
        
        Models to try:
        - google/flan-t5-small (80MB, fast)
        - google/flan-t5-base (250MB, balanced)
        - google/flan-t5-large (780MB, better quality)
        """
        self.model_name = model_name
        self.max_length = max_length
        self.temperature = temperature
        
        print(f"\nInitializing FREE Local LLM...")
        print(f"Model: {model_name}")
        print(f"Downloading model (one-time)...")
        
        self.pipeline = pipeline(
            "text2text-generation",
            model=model_name,
            max_length=max_length,
            temperature=temperature
        )
        
        print(f"✓ FREE LLM initialized")
    
    def generate_response(self, prompt: str, retry_attempts: int = 1) -> str:
        """Generate response"""
        try:
            result = self.pipeline(prompt)[0]['generated_text']
            return result
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    def generate_response_with_context(
        self,
        question: str,
        context_documents: List[Document],
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate response with RAG context"""
        
        # Build context
        context_text = "\n\n".join([
            f"Source: {doc.metadata.get('category', 'Unknown')}\n{doc.page_content}"
            for doc in context_documents[:3]  # Limit to top 3 for local model
        ])
        
        # Build prompt
        prompt = f"""Context: {context_text}

Question: {question}

Answer based on the context above:"""
        
        return self.generate_response(prompt[:1000])  # Limit length
    
    def generate_chat_response(
        self,
        question: str,
        context_documents: List[Document],
        conversation_history: Optional[List] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate chat response"""
        return self.generate_response_with_context(question, context_documents, system_prompt)


if __name__ == "__main__":
    # Test
    llm = FreeLLM()
    response = llm.generate_response("What is COMSATS University?")
    print(f"\nResponse: {response}")
