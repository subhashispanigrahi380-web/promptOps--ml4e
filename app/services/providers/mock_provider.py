import asyncio
import time
from typing import Dict, Any, Optional, AsyncGenerator
from app.services.providers.base import LLMProvider
from app.models.schemas import GenerationResponse, UsageStats

class MockProvider(LLMProvider):
    def __init__(self, delay_ms: int = 150):
        self.delay_ms = delay_ms

    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> GenerationResponse:
        start = time.time()
        await asyncio.sleep(self.delay_ms / 1000.0)

        # Dynamic mock response generated to strictly conform to schema
        content: Any = {}
        if json_schema and "properties" in json_schema:
            props = json_schema["properties"]
            for key, spec in props.items():
                t = spec.get("type", "string")
                if t == "string":
                    if "date" in key.lower():
                        content[key] = "2026-10-15"
                    elif "time" in key.lower():
                        content[key] = "10:00 AM - 11:30 AM"
                    elif "email" in key.lower():
                        content[key] = "alex.rivera@promptops.ai"
                    elif "phone" in key.lower():
                        content[key] = "+1 (555) 234-5678"
                    elif "url" in key.lower() or "link" in key.lower():
                        content[key] = "https://promptops.ai/careers"
                    else:
                        content[key] = f"Sample {key.replace('_', ' ').title()}"
                elif t == "array":
                    items_spec = spec.get("items", {})
                    if items_spec.get("type") == "object":
                        sub_props = items_spec.get("properties", {})
                        sample_obj = {k: f"Sample {k}" for k in sub_props.keys()}
                        content[key] = [sample_obj]
                    else:
                        content[key] = [f"Item 1 for {key}", f"Item 2 for {key}"]
                elif t == "number" or t == "integer":
                    content[key] = 42
                elif t == "boolean":
                    content[key] = True
                else:
                    content[key] = f"Mock {key}"
        else:
            content = f"Mock response completed for prompt input."

        latency = int((time.time() - start) * 1000)
        return GenerationResponse(
            content=content,
            usage=UsageStats(prompt_tokens=45, completion_tokens=85, total_tokens=130, estimated_cost=0.0),
            latency_ms=latency,
            model_used=model_override or "mock-deterministic-v2",
            validation_status="PASSED",
            retry_count=0
        )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        chunks = ["{\n", '  "status": ', '"mock_stream_active",\n', '  "tokens": ', '100\n', "}\n"]
        for c in chunks:
            await asyncio.sleep(0.04)
            yield c
