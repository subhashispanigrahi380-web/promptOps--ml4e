from typing import Dict, Any, Optional
from app.services.providers.base import LLMProvider
from app.services.providers.gemini_provider import GeminiProvider, get_gemini_key
from app.services.providers.openai_compatible import OpenAIProvider, GroqProvider, get_secret
from app.services.providers.mock_provider import MockProvider

class ModelRouter:
    """
    Intelligent Model Router that resolves the appropriate LLM provider
    based on task type, provider choice, or available credentials.
    """
    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {
            "gemini": GeminiProvider(default_model="gemini-1.5-flash"),
            "gemini-pro": GeminiProvider(default_model="gemini-1.5-pro"),
            "gemini-2.0": GeminiProvider(default_model="gemini-2.0-flash"),
            "groq": GroqProvider(default_model="llama-3.1-8b-instant"),
            "groq-fast": GroqProvider(default_model="llama-3.1-8b-instant"),
            "groq-70b": GroqProvider(default_model="llama3-70b-8192"),
            "openai": OpenAIProvider(default_model="gpt-4o-mini"),
            "openai-quality": OpenAIProvider(default_model="gpt-4o"),
            "mock": MockProvider()
        }

    def route(self, task_type_or_provider: str, api_key_override: Optional[str] = None) -> LLMProvider:
        key = (task_type_or_provider or "gemini").lower().strip()

        # Direct provider match
        if key in self.providers:
            return self.providers[key]

        # Semantic task type routing
        if key in ("extraction", "fast"):
            # Prefer Gemini Flash, then Groq, then fallback
            if get_gemini_key(api_key_override):
                return self.providers["gemini"]
            elif get_secret("GROQ_API_KEY", api_key_override):
                return self.providers["groq-fast"]
            elif get_secret("OPENAI_API_KEY", api_key_override):
                return self.providers["openai"]
            return self.providers["mock"]

        elif key in ("complex_reasoning", "quality"):
            # Prefer Gemini 1.5 Pro or OpenAI GPT-4o
            if get_gemini_key(api_key_override):
                return self.providers["gemini-pro"]
            elif get_secret("OPENAI_API_KEY", api_key_override):
                return self.providers["openai-quality"]
            return self.providers["mock"]

        # Default fallback to Gemini if key available, otherwise Mock
        if get_gemini_key(api_key_override):
            return self.providers["gemini"]
        return self.providers["mock"]
