import json
import asyncio
import time
from typing import Dict, Any, Optional, AsyncGenerator
from app.services.llm_base import LLMProvider
from app.models.schemas import GenerationResponse, UsageStats

class MockLLM(LLMProvider):
    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms

    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> GenerationResponse:
        start_time = time.time()
        await asyncio.sleep(self.delay_ms / 1000.0)
        
        # If schema is provided, return a deterministic valid JSON response based on the schema keys
        if json_schema and "properties" in json_schema:
            content = {k: f"mock_value_for_{k}" for k in json_schema["properties"].keys()}
        else:
            content = f"Mock response for: {prompt[:20]}..."
            
        latency = int((time.time() - start_time) * 1000)
        
        return GenerationResponse(
            content=content,
            usage=UsageStats(prompt_tokens=10, completion_tokens=20, total_tokens=30, estimated_cost=0.0001),
            latency_ms=latency,
            model_used="mock-model-v1"
        )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        words = ["This ", "is ", "a ", "mock ", "streaming ", "response."]
        for word in words:
            await asyncio.sleep(0.05)
            yield word
