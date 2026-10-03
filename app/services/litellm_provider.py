import time
import json
from typing import Dict, Any, Optional, AsyncGenerator
import litellm
from app.services.llm_base import LLMProvider
from app.models.schemas import GenerationResponse, UsageStats

class LiteLLMProvider(LLMProvider):
    def __init__(self, default_model: str = "gpt-3.5-turbo"):
        self.default_model = default_model

    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> GenerationResponse:
        start_time = time.time()
        
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        model = kwargs.get("model", self.default_model)
        
        responseformat = None
        if json_schema:
            # Note: LiteLLM supports passing JSON schema to some providers like OpenAI
            responseformat = {"type": "json_object"}
            # We'd typically inject the schema into the prompt if the provider doesn't support structured outputs directly
            messages[0]["content"] += f"\n\nYou MUST return valid JSON adhering to this schema:\n{json.dumps(json_schema)}"

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                response_format=responseformat,
                **kwargs
            )
            
            latency = int((time.time() - start_time) * 1000)
            
            content = response.choices[0].message.content
            if json_schema:
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass # Will be handled by validation layer later

            usage = response.usage
            cost = litellm.completion_cost(completion_response=response) or 0.0

            return GenerationResponse(
                content=content,
                usage=UsageStats(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    estimated_cost=cost
                ),
                latency_ms=latency,
                model_used=model
            )
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=latency,
                model_used=model,
                error=str(e)
            )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        model = kwargs.get("model", self.default_model)
        
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
