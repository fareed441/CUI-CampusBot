"""
Perplexity LLM Integration
Uses Perplexity API (chat/completions endpoint) for text generation.
Supports simple chat history and RAG-style context injection.

Set API key in PowerShell before running:
  $env:PPLX_API_KEY = "pplx-..."
Optionally override model:
  $env:PPLX_MODEL = "sonar-reasoning"

Models (examples):
  sonar | sonar-pro | sonar-reasoning | sonar-reasoning-pro | sonar-deep-research
"""

import os
import time
import json
import re
import requests
from typing import List, Dict, Optional
from langchain_core.documents import Document

# Defaults (can be overridden via config/env)
PPLX_API_URL = os.getenv("PPLX_API_URL", "https://api.perplexity.ai/chat/completions")
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar")
PPLX_TEMPERATURE = float(os.getenv("PPLX_TEMPERATURE", "0.7"))
PPLX_MAX_RETRIES = int(os.getenv("PPLX_MAX_RETRIES", "5"))
PPLX_TIMEOUT = int(os.getenv("PPLX_TIMEOUT", "30"))

# Urdu/Arabic Unicode detection pattern
URDU_SCRIPT_PATTERN = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')


def contains_urdu_script(text: str) -> bool:
    """Check if text contains Arabic/Urdu script characters"""
    return bool(URDU_SCRIPT_PATTERN.search(text))


class PerplexityLLM:
    """Wrapper around Perplexity Chat Completions API"""
    def __init__(
        self,
        api_key: str,
        model_name: str = PPLX_MODEL,
        temperature: float = PPLX_TEMPERATURE,
        max_retries: int = PPLX_MAX_RETRIES,
        timeout: int = PPLX_TIMEOUT,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("Perplexity API key not provided. Set $env:PPLX_API_KEY.")

        print("✓ Perplexity LLM configured")
        print(f"  Model: {self.model_name}")
        print(f"  Temperature: {self.temperature}")

    def _call_api(self, messages: List[Dict[str, str]]) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(PPLX_API_URL, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
                # Retry on transient
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    wait = 2 * attempt
                    try:
                        msg = resp.json().get("error", {}).get("message", resp.text[:100])
                    except Exception:
                        msg = resp.text[:100]
                    print(f"Transient {resp.status_code} ({msg}); retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"Perplexity API error {resp.status_code}: {resp.text}")
            except requests.RequestException as e:
                last_error = e
                if attempt == self.max_retries:
                    break
                wait = 2 * attempt
                print(f"Network error ({e}); retrying in {wait}s...")
                time.sleep(wait)
        raise RuntimeError(f"Request failed after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _extract_content(response: Dict) -> str:
        try:
            return response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return json.dumps(response)[:500]

    def _transliterate_to_roman(self, text: str) -> str:
        """Convert Urdu script text to Roman Urdu using LLM"""
        transliterate_prompt = f"""Convert this text to Roman Urdu using ONLY English/Latin letters (A-Z, a-z).

RULES:
1. Convert ALL Arabic/Urdu script to Roman Urdu (Latin letters).
2. Keep the EXACT same meaning - just change the script.
3. DO NOT add any new information.
4. Technical English words stay as-is.
5. Output MUST contain ZERO Arabic/Urdu script characters.

Examples:
- "السلام علیکم" → "Assalam o alaikum"
- "آپ کیسے ہیں" → "Aap kese hain"
- "داخلے" → "dakhlay" or "admission"

Text to convert:
{text}

Roman Urdu output (ONLY Latin letters):"""
        
        messages = [
            {"role": "system", "content": "You are a transliterator. Convert Urdu script to Roman Urdu using ONLY English/Latin letters. Output must contain NO Arabic/Urdu characters."},
            {"role": "user", "content": transliterate_prompt},
        ]
        
        try:
            resp = self._call_api(messages)
            result = self._extract_content(resp)
            # Verify the result doesn't contain Urdu script
            if contains_urdu_script(result):
                # If still has Urdu script, try one more time with stricter prompt
                messages[1]["content"] = f"STRICTLY convert to Latin letters ONLY. NO Arabic/Urdu script allowed. Text: {text}"
                resp = self._call_api(messages)
                result = self._extract_content(resp)
            return result
        except Exception as e:
            print(f"Transliteration failed: {e}")
            return text  # Return original if transliteration fails

    def _ensure_roman_urdu(self, text: str, is_roman_mode: bool) -> str:
        """Ensure text is in Roman Urdu (Latin script) if in Roman Urdu mode"""
        if not is_roman_mode:
            return text
        
        if contains_urdu_script(text):
            print("[Roman Urdu] Detected Urdu script in output, transliterating...")
            return self._transliterate_to_roman(text)
        return text

    def generate_response(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ]
        resp = self._call_api(messages)
        return self._extract_content(resp)

    def generate_response_with_context(
        self,
        question: str,
        context_documents: List[Document],
        system_prompt: Optional[str] = None,
        language_instruction: Optional[str] = None,
        is_roman_mode: bool = False,
    ) -> str:
        sys_msg = system_prompt or "You are a helpful assistant. Use the provided context."
        
        # Handle empty context - still respond to greetings and conversational queries
        if context_documents:
            context_text = "\n\n---\n\n".join([
                f"{doc.page_content}"
                for doc in context_documents[:5]
            ])
            user_msg = f"""Based on the following information from CUI Vehari Campus database:

{context_text}

User Question: {question}

Provide an accurate answer using the information above. If the question is not CUI-related, politely decline."""
        else:
            # No context found - handle conversationally
            user_msg = f"""User Question: {question}

Note: No specific CUI campus information was found for this query. If this is a greeting or conversational message, respond warmly and offer to help with CUI campus queries. If it's a CUI-specific question, apologize that you don't have that specific information in the knowledge base."""
        
        # Append language instruction to enforce output language
        if language_instruction:
            user_msg += language_instruction
        
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]
        resp = self._call_api(messages)
        result = self._extract_content(resp)
        
        # Validate and fix Roman Urdu output if needed
        return self._ensure_roman_urdu(result, is_roman_mode)

    def generate_chat_response(
        self,
        question: str,
        context_documents: List[Document],
        conversation_history: Optional[List[Dict]] = None,
        system_prompt: Optional[str] = None,
        language_instruction: Optional[str] = None,
        is_roman_mode: bool = False,
    ) -> str:
        sys_msg = system_prompt or "You are a helpful assistant for COMSATS University Islamabad."
        messages = [{"role": "system", "content": sys_msg}]
        if conversation_history:
            for turn in conversation_history[-6:]:  # limit history
                messages.append({"role": "user", "content": turn.get("question", "")})
                messages.append({"role": "assistant", "content": turn.get("answer", "")})
        # Handle context - allow conversational responses for greetings
        if context_documents:
            context_text = "\n\n---\n\n".join([
                doc.page_content for doc in context_documents[:5]
            ])
            user_msg = f"""Based on the following information from CUI Vehari Campus database:

{context_text}

User Question: {question}

Provide an accurate answer using the information above."""
        else:
            # No context found - handle conversationally
            user_msg = f"""User Question: {question}

Note: No specific CUI campus information was found for this query. If this is a greeting or conversational message, respond warmly and offer to help with CUI campus queries. If it's a CUI-specific question, apologize that you don't have that specific information in the knowledge base."""
        
        # Append language instruction to enforce output language
        if language_instruction:
            user_msg += language_instruction
        
        messages.append({"role": "user", "content": user_msg})
        resp = self._call_api(messages)
        result = self._extract_content(resp)
        
        # Validate and fix Roman Urdu output if needed
        return self._ensure_roman_urdu(result, is_roman_mode)

if __name__ == "__main__":
    api_key = os.getenv("PPLX_API_KEY", "")
    if not api_key:
        print("Set PPLX_API_KEY environment variable first.")
    else:
        llm = PerplexityLLM(api_key=api_key)
        print(llm.generate_response("Explain RAG architecture briefly."))
