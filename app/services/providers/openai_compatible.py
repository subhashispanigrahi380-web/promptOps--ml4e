import os
import time
import json
import httpx
from typing import Dict, Any, Optional, AsyncGenerator
from app.services.providers.base import LLMProvider, estimate_cost
from app.models.schemas import GenerationResponse, UsageStats

def get_secret(key_name: str, override: Optional[str] = None) -> Optional[str]:
    """Retrieve secret from override, environment variable, or Streamlit secrets."""
    if override and override.strip():
        return override.strip()
    val = os.getenv(key_name)
    if val and val.strip():
        return val.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key_name in st.secrets:
            return st.secrets[key_name]
    except Exception:
        pass
    return None

class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        default_model: str,
        api_key_env_var: str,
        provider_name: str
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.api_key_env_var = api_key_env_var
        self.provider_name = provider_name

    async def generate(
        self, 
        prompt: str, 
        system_message: Optional[str] = None, 
        json_schema: Optional[Dict[str, Any]] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> GenerationResponse:
        start_time = time.time()
        api_key = get_secret(self.api_key_env_var, api_key_override)
        model = model_override or self.default_model

        if not api_key:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=0,
                model_used=model,
                error=f"{self.api_key_env_var} not found. Please provide it in environment or Streamlit secrets."
            )

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        user_prompt = prompt
        if json_schema:
            user_prompt += f"\n\nRespond ONLY with a valid JSON object matching this schema:\n{json.dumps(json_schema, indent=2)}"
        
        messages.append({"role": "user", "content": user_prompt})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"} if json_schema else None
        }
        # Filter out None values
        payload = {k: v for k, v in payload.items() if v is not None}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                latency = int((time.time() - start_time) * 1000)

                if res.status_code != 200:
                    err_msg = res.json().get("error", {}).get("message", res.text)
                    return GenerationResponse(
                        content="",
                        usage=UsageStats(),
                        latency_ms=latency,
                        model_used=model,
                        error=f"{self.provider_name} Error ({res.status_code}): {err_msg}"
                    )

                data = res.json()
                choice = data["choices"][0]["message"]["content"]
                
                # Attempt to parse json
                try:
                    content = json.loads(choice)
                except json.JSONDecodeError:
                    content = choice

                usage_data = data.get("usage", {})
                p_toks = usage_data.get("prompt_tokens", len(prompt) // 4)
                c_toks = usage_data.get("completion_tokens", len(choice) // 4)
                tot_toks = usage_data.get("total_tokens", p_toks + c_toks)
                cost = estimate_cost(model, p_toks, c_toks)

                return GenerationResponse(
                    content=content,
                    usage=UsageStats(
                        prompt_tokens=p_toks,
                        completion_tokens=c_toks,
                        total_tokens=tot_toks,
                        estimated_cost=cost
                    ),
                    latency_ms=latency,
                    model_used=model
                )

        except httpx.TimeoutException:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=int((time.time() - start_time) * 1000),
                model_used=model,
                error=f"{self.provider_name} request timed out after 30 seconds."
            )
        except Exception as e:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=int((time.time() - start_time) * 1000),
                model_used=model,
                error=f"{self.provider_name} connection error: {str(e)}"
            )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        api_key = get_secret(self.api_key_env_var, api_key_override)
        model = model_override or self.default_model
        if not api_key:
            yield f"[Error: {self.api_key_env_var} missing]"
            return

        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": model, "messages": messages, "stream": True}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: ") and line.strip() != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except Exception:
                                pass
        except Exception as e:
            yield f"[{self.provider_name} Streaming Error: {str(e)}]"

# ==============================================================================
# Concrete Provider Classes
# ==============================================================================

class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, default_model: str = "gpt-4o-mini"):
        super().__init__(
            base_url="https://api.openai.com/v1",
            default_model=default_model,
            api_key_env_var="OPENAI_API_KEY",
            provider_name="OpenAI"
        )

class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, default_model: str = "llama-3.3-70b-versatile"):
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            default_model=default_model,
            api_key_env_var="GROQ_API_KEY",
            provider_name="Groq"
        )
