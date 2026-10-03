import time
from typing import Dict, Any, Optional
from jinja2 import Template
from app.models.schemas import GenerationRequest, GenerationResponse, UsageStats
from app.services.llm_base import LLMProvider
from app.services.registry import PromptRegistry
from app.services.validator import OutputValidator
from app.services import cache as Cache

class GenerationService:
    def __init__(self, provider: LLMProvider, registry: PromptRegistry, max_retries: int = 2):
        self.provider = provider
        self.registry = registry
        self.max_retries = max_retries

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        # ── 1. Cache Check ─────────────────────────────────────
        cached = Cache.get_cached(request.prompt_id, request.variables, request.task_type)
        if cached:
            cached.cached = True
            return cached

        # ── 2. Fetch prompt from registry ───────────────────────
        prompt_parts = request.prompt_id.rsplit('_v', 1)
        if len(prompt_parts) == 2 and prompt_parts[1].isdigit():
            name, version = prompt_parts[0], int(prompt_parts[1])
        else:
            name, version = request.prompt_id, None

        prompt_def = self.registry.get_prompt(name, version)
        if not prompt_def:
            return GenerationResponse(
                content="", usage=UsageStats(), latency_ms=0, model_used="none",
                error=f"Prompt '{request.prompt_id}' not found in registry."
            )

        # ── 3. Render Jinja2 Template ───────────────────────────
        try:
            rendered_prompt = Template(prompt_def.template).render(**request.variables)
        except Exception as e:
            return GenerationResponse(
                content="", usage=UsageStats(), latency_ms=0, model_used="none",
                error=f"Template rendering error: {str(e)}"
            )

        # ── 4. Generation + Repair Loop ─────────────────────────
        current_prompt = rendered_prompt
        last_error = None
        total_usage = UsageStats()
        total_latency = 0

        for attempt in range(self.max_retries + 1):
            response = await self.provider.generate(
                prompt=current_prompt,
                json_schema=prompt_def.schema_def
            )

            total_usage.prompt_tokens     += response.usage.prompt_tokens
            total_usage.completion_tokens += response.usage.completion_tokens
            total_usage.total_tokens      += response.usage.total_tokens
            total_usage.estimated_cost    += response.usage.estimated_cost
            total_latency                 += response.latency_ms

            # Provider-level error (timeout / network)
            if response.error:
                return GenerationResponse(
                    content="", usage=total_usage, latency_ms=total_latency,
                    model_used=response.model_used, error=response.error
                )

            # ── 5. Validate ─────────────────────────────────────
            if prompt_def.schema_def:
                is_valid, err_msg = OutputValidator.validate(response.content, prompt_def.schema_def)
                if is_valid:
                    result = GenerationResponse(
                        content=response.content,
                        usage=total_usage,
                        latency_ms=total_latency,
                        model_used=response.model_used
                    )
                    Cache.set_cache(request.prompt_id, request.variables, request.task_type, result)
                    return result
                else:
                    last_error = err_msg
                    # Repair: feed the error back to the model
                    current_prompt = (
                        f"{rendered_prompt}\n\n"
                        f"[REPAIR ATTEMPT {attempt + 1}] "
                        f"Previous output was invalid: {err_msg}\n"
                        f"Fix the JSON so it strictly matches the required schema."
                    )
            else:
                result = GenerationResponse(
                    content=response.content,
                    usage=total_usage,
                    latency_ms=total_latency,
                    model_used=response.model_used
                )
                Cache.set_cache(request.prompt_id, request.variables, request.task_type, result)
                return result

        return GenerationResponse(
            content="",
            usage=total_usage,
            latency_ms=total_latency,
            model_used=self.provider.__class__.__name__,
            error=f"Max retries ({self.max_retries}) exceeded. Last error: {last_error}"
        )
