import os
import time
import json
import httpx
from typing import Dict, Any, Optional, List, AsyncGenerator
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
        self.cached_working_model: Optional[str] = None
        self.api_versions = ["v1beta", "v1"]

    async def _discover_available_model(self, client: httpx.AsyncClient, api_key: str) -> Optional[str]:
        """Queries Google's ListModels API to find active models supported by this key."""
        for ver in self.api_versions:
            url = f"https://generativelanguage.googleapis.com/{ver}/models?key={api_key}"
            try:
                r = await client.get(url, timeout=10.0)
                if r.status_code == 200:
                    models = r.json().get("models", [])
                    gen_models = [
                        m["name"] for m in models 
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                    # Clean 'models/' prefix if present
                    clean_names = [m.replace("models/", "") for m in gen_models]
                    
                    # Preference priority
                    for candidate in ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-pro", "gemini-1.5-pro"]:
                        if candidate in clean_names:
                            return candidate
                    if clean_names:
                        return clean_names[0]
            except Exception:
                continue
        return None

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
        requested_model = model_override or self.cached_working_model or self.default_model
        # Strip models/ prefix if accidentally passed
        model = requested_model.replace("models/", "")

        if not api_key:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=0,
                model_used=model,
                error="GEMINI_API_KEY not found. Please paste it in the sidebar expander or set it in Streamlit secrets."
            )

        # Build payload
        user_content_text = prompt
        if json_schema:
            user_content_text += (
                f"\n\nCRITICAL REQUIREMENT: Respond ONLY with a valid JSON object matching this schema:\n"
                f"{json.dumps(json_schema, indent=2)}\n"
                f"Do not include code fences (```json). Output raw parseable JSON only."
            )

        payload = {
            "contents": [{"parts": [{"text": user_content_text}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        if system_message:
            payload["systemInstruction"] = {"parts": [{"text": system_message}]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try primary requested model and version
            models_to_try = [model]
            
            # Common fallback aliases if 404 occurs
            fallback_aliases = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-pro"]
            for a in fallback_aliases:
                if a not in models_to_try:
                    models_to_try.append(a)

            last_error = ""

            for current_model in models_to_try:
                for api_ver in self.api_versions:
                    url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{current_model}:generateContent?key={api_key}"
                    try:
                        res = await client.post(url, json=payload)
                        latency = int((time.time() - start_time) * 1000)

                        if res.status_code == 200:
                            self.cached_working_model = current_model
                            data = res.json()
                            candidates = data.get("candidates", [])
                            if not candidates:
                                return GenerationResponse(
                                    content="", usage=UsageStats(), latency_ms=latency, model_used=current_model,
                                    error="Gemini returned empty candidate list."
                                )

                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            
                            cleaned_text = raw_text.strip()
                            if cleaned_text.startswith("```json"):
                                cleaned_text = cleaned_text[7:]
                            if cleaned_text.startswith("```"):
                                cleaned_text = cleaned_text[3:]
                            if cleaned_text.endswith("```"):
                                cleaned_text = cleaned_text[:-3]
                            cleaned_text = cleaned_text.strip()

                            try:
                                parsed_content = json.loads(cleaned_text)
                            except json.JSONDecodeError:
                                parsed_content = cleaned_text

                            usage_meta = data.get("usageMetadata", {})
                            prompt_toks = usage_meta.get("promptTokenCount", len(prompt) // 4)
                            comp_toks = usage_meta.get("candidatesTokenCount", len(raw_text) // 4)
                            tot_toks = usage_meta.get("totalTokenCount", prompt_toks + comp_toks)
                            cost = estimate_cost(current_model, prompt_toks, comp_toks)

                            return GenerationResponse(
                                content=parsed_content,
                                usage=UsageStats(
                                    prompt_tokens=prompt_toks,
                                    completion_tokens=comp_toks,
                                    total_tokens=tot_toks,
                                    estimated_cost=cost
                                ),
                                latency_ms=latency,
                                model_used=current_model
                            )
                        
                        elif res.status_code == 404:
                            # Model not found in this version, proceed to next fallback
                            last_error = res.json().get("error", {}).get("message", res.text)
                            continue
                        elif res.status_code == 400 and "responseMimeType" in res.text:
                            # Older models (like gemini-pro) don't support responseMimeType
                            payload["generationConfig"].pop("responseMimeType", None)
                            retry_res = await client.post(url, json=payload)
                            if retry_res.status_code == 200:
                                self.cached_working_model = current_model
                                raw_text = retry_res.json()["candidates"][0]["content"]["parts"][0]["text"]
                                try:
                                    parsed_content = json.loads(raw_text.strip().strip("`").replace("json", "").strip())
                                except Exception:
                                    parsed_content = raw_text
                                return GenerationResponse(
                                    content=parsed_content,
                                    usage=UsageStats(prompt_tokens=50, completion_tokens=50, total_tokens=100),
                                    latency_ms=latency,
                                    model_used=current_model
                                )
                        else:
                            # Quota, Auth, or Permission errors
                            err_msg = res.json().get("error", {}).get("message", res.text)
                            return GenerationResponse(
                                content="",
                                usage=UsageStats(),
                                latency_ms=latency,
                                model_used=current_model,
                                error=f"Gemini API Error ({res.status_code}): {err_msg}"
                            )

                    except httpx.TimeoutException:
                        return GenerationResponse(
                            content="", usage=UsageStats(), latency_ms=int((time.time() - start_time) * 1000),
                            model_used=current_model, error="Gemini request timed out after 30 seconds."
                        )
                    except Exception as e:
                        last_error = str(e)
                        continue

            # If all standard fallbacks returned 404, query ListModels dynamically
            discovered_model = await self._discover_available_model(client, api_key)
            if discovered_model and discovered_model not in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{discovered_model}:generateContent?key={api_key}"
                try:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        self.cached_working_model = discovered_model
                        raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                        try:
                            parsed_content = json.loads(raw_text.strip())
                        except Exception:
                            parsed_content = raw_text
                        return GenerationResponse(
                            content=parsed_content,
                            usage=UsageStats(prompt_tokens=50, completion_tokens=50, total_tokens=100),
                            latency_ms=int((time.time() - start_time) * 1000),
                            model_used=discovered_model
                        )
                except Exception:
                    pass

            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=int((time.time() - start_time) * 1000),
                model_used=model,
                error=f"Gemini Model '{model}' not accessible on your key: {last_error}"
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
        model = (model_override or self.cached_working_model or self.default_model).replace("models/", "")
        if not api_key:
            yield "[Error: GEMINI_API_KEY missing]"
            return

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}"
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
