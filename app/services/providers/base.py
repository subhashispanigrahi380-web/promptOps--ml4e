from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator
from app.models.schemas import GenerationResponse

# Current token pricing (per 1,000,000 tokens)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Google Gemini
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.00},
    "gemini-2.0-flash": {"prompt": 0.10, "completion": 0.40},
    # Groq (Llama)
    "llama-3.3-70b-versatile": {"prompt": 0.59, "completion": 0.79},
    "llama-3.1-8b-instant": {"prompt": 0.05, "completion": 0.08},
    # OpenAI
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
    # Default fallback
    "mock": {"prompt": 0.0, "completion": 0.0},
}

def estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculates estimated USD cost based on token counts and pricing table."""
    pricing = None
    for key, price in MODEL_PRICING.items():
        if key in model_name.lower():
            pricing = price
            break
    if not pricing:
        pricing = {"prompt": 0.10, "completion": 0.30}  # conservative default
    
    cost = (prompt_tokens / 1_000_000 * pricing["prompt"]) + (completion_tokens / 1_000_000 * pricing["completion"])
    return round(cost, 6)

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> GenerationResponse:
        """Execute non-streaming completion adhering to optional json_schema."""
        pass

    @abstractmethod
    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Execute token-by-token streaming completion."""
        pass
