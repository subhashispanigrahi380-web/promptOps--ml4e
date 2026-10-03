import os
import time
import json
import httpx
from typing import Dict, Any, Optional, AsyncGenerator
from app.services.providers.base import LLMProvider, estimate_cost
from app.models.schemas import GenerationResponse, UsageStats

def get_gemini_key(api_key_override: Optional[str] = None) -> Optional[str]:
    """Retrieve Gemini API key from override, env vars, or Streamlit secrets."""
    if api_key_override and api_key_override.strip():
        return api_key_override.strip()
    
    # 1. Environment variable
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    
    # 2. Streamlit Cloud Secrets (if running in Streamlit)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    
    return None

class GeminiProvider(LLMProvider):
    def __init__(self, default_model: str = "gemini-1.5-flash"):
        self.default_model = default_model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

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
        api_key = get_gemini_key(api_key_override)
        model = model_override or self.default_model

        if not api_key:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=0,
                model_used=model,
                error="GEMINI_API_KEY not found. Set it in environment variables, Streamlit secrets, or enter it in the UI."
            )

        # Build payload with structured JSON configuration
        system_instruction_part = None
        if system_message:
            system_instruction_part = {"parts": [{"text": system_message}]}

        user_content_text = prompt
        if json_schema:
            user_content_text += (
                f"\n\nCRITICAL REQUIREMENT: You MUST respond ONLY with valid JSON conforming to this JSON Schema:\n"
                f"{json.dumps(json_schema, indent=2)}\n"
                f"Do not include markdown codeblocks (no ```json). Output raw parseable JSON object only."
            )

        payload = {
            "contents": [{"parts": [{"text": user_content_text}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        if system_instruction_part:
            payload["systemInstruction"] = system_instruction_part

        url = f"{self.base_url}/{model}:generateContent?key={api_key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                latency = int((time.time() - start_time) * 1000)

                if res.status_code != 200:
                    error_data = res.json().get("error", {})
                    msg = error_data.get("message", res.text)
                    return GenerationResponse(
                        content="",
                        usage=UsageStats(),
                        latency_ms=latency,
                        model_used=model,
                        error=f"Gemini API Error ({res.status_code}): {msg}"
                    )

                data = res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return GenerationResponse(
                        content="",
                        usage=UsageStats(),
                        latency_ms=latency,
                        model_used=model,
                        error="Gemini returned empty candidate response."
                    )

                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                # Clean any stray markdown fences if model added them
                cleaned_text = raw_text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                cleaned_text = cleaned_text.strip()

                # Attempt to parse into JSON dict
                parsed_content = cleaned_text
                try:
                    parsed_content = json.loads(cleaned_text)
                except json.JSONDecodeError:
                    parsed_content = cleaned_text

                # Parse usage metadata
                usage_meta = data.get("usageMetadata", {})
                prompt_toks = usage_meta.get("promptTokenCount", len(prompt) // 4)
                comp_toks = usage_meta.get("candidatesTokenCount", len(raw_text) // 4)
                tot_toks = usage_meta.get("totalTokenCount", prompt_toks + comp_toks)
                cost = estimate_cost(model, prompt_toks, comp_toks)

                return GenerationResponse(
                    content=parsed_content,
                    usage=UsageStats(
                        prompt_tokens=prompt_toks,
                        completion_tokens=comp_toks,
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
                error="Gemini API request timed out after 30 seconds."
            )
        except Exception as e:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=int((time.time() - start_time) * 1000),
                model_used=model,
                error=f"Gemini connection error: {str(e)}"
            )

    async def generate_stream(
        self, 
        prompt: str, 
        system_message: Optional[str] = None,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        api_key = get_gemini_key(api_key_override)
        model = model_override or self.default_model
        if not api_key:
            yield "[Error: GEMINI_API_KEY missing]"
            return

        url = f"{self.base_url}/{model}:streamGenerateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                chunk_json = json.loads(line.lstrip("data: "))
                                text = chunk_json["candidates"][0]["content"]["parts"][0]["text"]
                                yield text
                            except Exception:
                                pass
        except Exception as e:
            yield f"[Streaming Error: {str(e)}]"
