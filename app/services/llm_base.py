from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncGenerator
from app.models.schemas import GenerationResponse

class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> GenerationResponse:
        """Generate a complete response."""
        pass

    @abstractmethod
    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming text response."""
        pass
