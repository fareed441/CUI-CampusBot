"""
Gemini LLM Integration using Google AI Studio API
Handles response generation using Gemini Pro model
"""

import os
import time
from typing import List, Dict, Optional
import google.generativeai as genai
from langchain_core.documents import Document


class GeminiLLM:
    """
    Google Gemini LLM for generating contextually accurate responses
    Uses Google AI Studio API Key
    """
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-exp",
        temperature: float = 0.7,
        max_output_tokens: int = 1024,
        top_p: float = 0.8,
        top_k: int = 40
    ):
        """
        Initialize Gemini LLM
        
        Args:
            api_key: Google API Key from AI Studio
            model_name: Gemini model name
            temperature: Creativity level (0.0 - 1.0)
            max_output_tokens: Maximum tokens in response
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
        """
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.top_p = top_p
        self.top_k = top_k
        
        # Configure Gemini API
        self._configure_gemini()
        
        # Initialize model
        self.model = self._create_model()
        
        print(f"✓ Gemini LLM initialized successfully")
        print(f"  Model: {self.model_name}")
        print(f"  Temperature: {self.temperature}")
    
    def _configure_gemini(self):
        """
        Configure Gemini API with API key
        """
        try:
            genai.configure(api_key=self.api_key)
            print(f"✓ Gemini API configured")
        except Exception as e:
            print(f"✗ Error configuring Gemini API: {str(e)}")
            raise
    
    def _create_model(self):
        """
        Create Gemini model instance with generation config
        
        Returns:
            GenerativeModel instance
        """
        try:
            generation_config = {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "max_output_tokens": self.max_output_tokens,
            }
            
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config
            )
            
            return model
        except Exception as e:
            print(f"✗ Error creating Gemini model: {str(e)}")
            raise
    
    def generate_response(
        self,
        prompt: str,
        retry_attempts: int = 3,
        retry_delay: float = 1.0
    ) -> str:
        """
        Generate response from Gemini
        
        Args:
            prompt: Input prompt
            retry_attempts: Number of retry attempts on failure
            retry_delay: Delay between retries in seconds
            
        Returns:
            Generated text response
        """
        for attempt in range(retry_attempts):
            try:
                response = self.model.generate_content(prompt)
                
                # Check if response has text
                if response and response.text:
                    return response.text
                else:
                    print(f"⚠ Empty response from Gemini (attempt {attempt + 1})")
                    
            except Exception as e:
                print(f"✗ Error generating response (attempt {attempt + 1}): {str(e)}")
                
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay)
                else:
                    return "I apologize, but I'm having trouble generating a response right now. Please try again."
        
        return "Unable to generate response after multiple attempts."
    
    def generate_response_with_context(
        self,
        question: str,
        context_documents: List[Document],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate response using retrieved context documents (RAG)
        
        Args:
            question: User's question
            context_documents: List of relevant documents from retrieval
            system_prompt: Optional system prompt for behavior customization
            
        Returns:
            Generated response
        """
        # Build context from documents
        context_parts = []
        for i, doc in enumerate(context_documents, 1):
            context_parts.append(f"[Context {i}]")
            context_parts.append(doc.page_content)
            context_parts.append("")
        
        context_text = "\n".join(context_parts)
        
        # Build prompt
        if system_prompt:
            prompt = f"""{system_prompt}

Context Information:
{context_text}

User Question: {question}

Please provide a clear and accurate answer based on the context above. If the context doesn't contain relevant information, politely indicate that."""
        else:
            prompt = f"""Based on the following context, please answer the user's question accurately.

Context:
{context_text}

Question: {question}

Answer:"""
        
        # Generate response
        return self.generate_response(prompt)
    
    def generate_chat_response(
        self,
        question: str,
        context_documents: List[Document],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate response with conversation history
        
        Args:
            question: Current question
            context_documents: Retrieved context
            conversation_history: Previous Q&A pairs
            system_prompt: System behavior prompt
            
        Returns:
            Generated response
        """
        # Build conversation context
        history_text = ""
        if conversation_history:
            history_parts = []
            for turn in conversation_history[-5:]:  # Last 5 turns
                history_parts.append(f"User: {turn.get('question', '')}")
                history_parts.append(f"Assistant: {turn.get('answer', '')}")
            history_text = "\n".join(history_parts)
        
        # Build document context
        context_parts = []
        for i, doc in enumerate(context_documents, 1):
            category = doc.metadata.get('category', 'General')
            context_parts.append(f"[{category} - Context {i}]")
            context_parts.append(doc.page_content)
            context_parts.append("")
        
        context_text = "\n".join(context_parts)
        
        # Build full prompt
        prompt_parts = []
        
        if system_prompt:
            prompt_parts.append(system_prompt)
            prompt_parts.append("")
        
        if history_text:
            prompt_parts.append("Previous Conversation:")
            prompt_parts.append(history_text)
            prompt_parts.append("")
        
        prompt_parts.append("Relevant Context:")
        prompt_parts.append(context_text)
        prompt_parts.append("")
        prompt_parts.append(f"Current Question: {question}")
        prompt_parts.append("")
        prompt_parts.append("Please provide a helpful and accurate answer:")
        
        prompt = "\n".join(prompt_parts)
        
        return self.generate_response(prompt)
    
    def test_connection(self) -> bool:
        """
        Test if Gemini API is working
        
        Returns:
            True if successful, False otherwise
        """
        try:
            test_response = self.generate_response("Say 'Hello'")
            return bool(test_response and len(test_response) > 0)
        except Exception as e:
            print(f"✗ Connection test failed: {str(e)}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Load API key from config
    from config import GOOGLE_API_KEY, GEMINI_MODEL_NAME, GEMINI_TEMPERATURE
    
    print("="*60)
    print("Gemini LLM Test")
    print("="*60)
    
    try:
        # Initialize Gemini
        gemini = GeminiLLM(
            api_key=GOOGLE_API_KEY,
            model_name=GEMINI_MODEL_NAME,
            temperature=GEMINI_TEMPERATURE
        )
        
        # Test 1: Simple generation
        print("\n1. Testing simple text generation:")
        response = gemini.generate_response("What is COMSATS University?")
        print(f"   Response: {response[:200]}...")
        
        # Test 2: RAG-style generation with context
        print("\n2. Testing context-based generation:")
        sample_docs = [
            Document(
                page_content="Question: What is CUI?\n\nAnswer: COMSATS University Islamabad (CUI) is a Federally Chartered, Public Sector University.",
                metadata={"category": "General", "source": "general_info.json"}
            ),
            Document(
                page_content="Question: How many campuses does CUI have?\n\nAnswer: CUI has seven campuses: Islamabad, Lahore, Abbottabad, Vehari, Wah, Attock, and Sahiwal.",
                metadata={"category": "General", "source": "general_info.json"}
            )
        ]
        
        question = "Tell me about COMSATS University and its campuses"
        response = gemini.generate_response_with_context(
            question=question,
            context_documents=sample_docs
        )
        print(f"   Question: {question}")
        print(f"   Response: {response[:300]}...")
        
        # Test 3: Connection test
        print("\n3. Testing API connection:")
        if gemini.test_connection():
            print("   ✓ Connection successful")
        else:
            print("   ✗ Connection failed")
        
        print("\n" + "="*60)
        print("✓ All tests completed!")
        
    except Exception as e:
        print(f"\n✗ Error during testing: {str(e)}")
        print("\nMake sure to:")
        print("1. Set GOOGLE_API_KEY in config.py")
        print("2. Ensure the API key is valid")
        print("3. Check internet connection")
