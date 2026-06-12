"""
CUI CampusBot - Multilingual RAG Query Handler
Handles queries in English, Urdu, and Roman Urdu

Features:
- Automatic language detection
- Multilingual embeddings (BGE-M3)
- Response in same language as query
"""

import logging
import re
from typing import Optional, Dict, List, Tuple
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import PPLX_API_KEY, PPLX_MODEL

logger = logging.getLogger(__name__)


# ===========================================
# Language Detection
# ===========================================

def detect_language(text: str) -> str:
    """
    Detect the language of the input text
    
    Returns:
        'en' for English
        'ur' for Urdu (Arabic script)
        'roman_urdu' for Roman Urdu (Urdu in Latin script)
    """
    # Check for Urdu Arabic script characters
    urdu_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    
    if urdu_pattern.search(text):
        return "ur"
    
    # Roman Urdu common words
    roman_urdu_words = [
        'kya', 'hai', 'hain', 'ho', 'mein', 'main', 'tum', 'aap', 'ye', 'yeh', 
        'wo', 'woh', 'ka', 'ki', 'ke', 'ko', 'se', 'par', 'ne', 'nahi', 'nahin',
        'kaise', 'kab', 'kahan', 'kyun', 'kaun', 'kitna', 'kitni', 'kitne',
        'acha', 'theek', 'bohat', 'bahut', 'zyada', 'kam', 'sab', 'kuch',
        'admission', 'fee', 'scholarship', 'campus', 'university',
        'batao', 'bataiye', 'bataye', 'chahiye', 'sakta', 'sakti', 'hoga', 'hogi',
        'mujhe', 'humein', 'apna', 'apni', 'apne', 'unka', 'uski', 'unke',
        'lekin', 'aur', 'ya', 'phir', 'abhi', 'pehle', 'baad', 'jab', 'tab',
        'comsats', 'vehari', 'lahore', 'islamabad', 'pakistan',
        'sir', 'madam', 'teacher', 'student', 'class', 'semester'
    ]
    
    # Convert text to lowercase and check for Roman Urdu words
    text_lower = text.lower()
    words = text_lower.split()
    
    roman_urdu_count = sum(1 for word in words if word in roman_urdu_words)
    
    # If more than 20% of words are Roman Urdu, classify as Roman Urdu
    if len(words) > 0 and (roman_urdu_count / len(words)) > 0.2:
        return "roman_urdu"
    
    # Default to English
    return "en"


def get_language_instruction(language: str) -> str:
    """Get instruction for LLM to respond in the detected language"""
    
    if language == "ur":
        return """
        اہم: صارف نے اردو میں سوال پوچھا ہے۔ براہ کرم اردو میں جواب دیں۔
        IMPORTANT: The user asked in Urdu. Please respond in Urdu (Arabic script).
        """
    elif language == "roman_urdu":
        return """
        IMPORTANT: The user asked in Roman Urdu (Urdu written in English letters).
        Please respond in Roman Urdu. Use simple, conversational Roman Urdu.
        Example: "Jee, COMSATS mein admission ke liye aap online apply kar sakte hain."
        """
    else:
        return """
        Please respond in clear, professional English.
        """


# ===========================================
# RAG Query Handler
# ===========================================

class MultilingualRAGHandler:
    """
    Handles RAG queries with multilingual support
    """
    
    def __init__(self):
        self.vectorstore = None
        self.llm = None
        self.embeddings = None
        
    def initialize(self):
        """Initialize RAG components"""
        from app.rag.startup_sync import get_vectorstore, get_embeddings
        
        self.vectorstore = get_vectorstore()
        self.embeddings = get_embeddings()
        self._initialize_llm()
        
        logger.info("[OK] Multilingual RAG Handler initialized")
    
    def _initialize_llm(self):
        """Initialize Perplexity LLM"""
        from langchain_community.chat_models import ChatPerplexity
        
        if not PPLX_API_KEY:
            logger.warning("Perplexity API key not set")
            return
        
        self.llm = ChatPerplexity(
            model=PPLX_MODEL,
            pplx_api_key=PPLX_API_KEY,
            temperature=0.3,
            max_tokens=1024
        )
        
        logger.info(f"[OK] Perplexity LLM initialized: {PPLX_MODEL}")
    
    def retrieve_context(self, query: str, k: int = 5) -> List[str]:
        """Retrieve relevant context from ChromaDB"""
        if self.vectorstore is None:
            from app.rag.startup_sync import get_vectorstore
            self.vectorstore = get_vectorstore()
        
        try:
            # Use similarity search
            docs = self.vectorstore.similarity_search(query, k=k)
            
            contexts = [doc.page_content for doc in docs]
            logger.info(f"Retrieved {len(contexts)} relevant chunks")
            
            return contexts
            
        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")
            return []
    
    def generate_response(self, query: str, contexts: List[str], language: str) -> str:
        """Generate response using LLM with context"""
        
        if self.llm is None:
            self._initialize_llm()
        
        if self.llm is None:
            return "Sorry, the AI model is not available at the moment."
        
        # Combine contexts
        context_text = "\n\n".join(contexts) if contexts else "No relevant information found."
        
        # Get language instruction
        lang_instruction = get_language_instruction(language)
        
        # Create prompt template
        prompt_template = """You are CUI CampusBot, an AI assistant for COMSATS University Islamabad, Vehari Campus.

{lang_instruction}

Based on the following context, answer the user's question accurately and helpfully.
If the context doesn't contain relevant information, say so politely.

CONTEXT:
{context}

USER QUESTION: {query}

ANSWER:"""
        
        prompt = PromptTemplate(
            input_variables=["context", "query", "lang_instruction"],
            template=prompt_template
        )
        
        try:
            # Generate response
            chain = prompt | self.llm | StrOutputParser()
            
            response = chain.invoke({
                "context": context_text,
                "query": query,
                "lang_instruction": lang_instruction
            })
            
            return response
            
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            if language == "ur":
                return "معذرت، جواب دینے میں مسئلہ ہوا۔ براہ کرم دوبارہ کوشش کریں۔"
            elif language == "roman_urdu":
                return "Maaf kijiye, jawab dene mein masla hua. Dobara try karein."
            else:
                return "Sorry, there was an error generating the response. Please try again."
    
    def query(self, user_query: str) -> Dict:
        """
        Main query method - handles complete RAG flow
        
        1. Detect language
        2. Retrieve relevant context
        3. Generate response in same language
        
        Returns:
            Dictionary with response and metadata
        """
        # Detect language
        language = detect_language(user_query)
        logger.info(f"Detected language: {language}")
        
        # Retrieve context
        contexts = self.retrieve_context(user_query)
        
        # Generate response
        response = self.generate_response(user_query, contexts, language)
        
        return {
            "answer": response,
            "language": language,
            "sources_count": len(contexts),
            "contexts": contexts[:3]  # Return top 3 for transparency
        }


# Global handler instance
_handler_instance: Optional[MultilingualRAGHandler] = None


def get_rag_handler() -> MultilingualRAGHandler:
    """Get or create the global RAG handler"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = MultilingualRAGHandler()
        _handler_instance.initialize()
    return _handler_instance


def query_rag(user_query: str) -> Dict:
    """
    Main function to query the RAG system
    
    Args:
        user_query: User's question in any supported language
    
    Returns:
        Dictionary with answer and metadata
    """
    handler = get_rag_handler()
    return handler.query(user_query)
