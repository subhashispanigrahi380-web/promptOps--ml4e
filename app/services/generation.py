import time
import json
from typing import Dict, Any, Optional, List
from jinja2 import Template
from app.models.schemas import GenerationRequest, GenerationResponse, UsageStats
from app.services.providers.base import LLMProvider
from app.services.registry import PromptRegistry
from app.services.validator import OutputValidator
from app.services import cache as Cache

class GenerationService:
    """
    Core Generation Orchestrator implementing schema validation,
    automatic repair retry loops, telemetry tracking, and response caching.
    """
    def __init__(self, provider: LLMProvider, registry: PromptRegistry, max_retries: int = 2):
        self.provider = provider
        self.registry = registry
        self.max_retries = max_retries

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        # 1. Cache Check
        cached_resp = Cache.get_cached(request.prompt_id, request.variables, request.task_type)
        if cached_resp:
            cached_resp.cached = True
            return cached_resp

        # 2. Retrieve Prompt Version
        prompt_parts = request.prompt_id.rsplit('_v', 1)
        if len(prompt_parts) == 2 and prompt_parts[1].isdigit():
            name, version = prompt_parts[0], int(prompt_parts[1])
        else:
            name, version = request.prompt_id, None

        prompt_def = self.registry.get_prompt(name, version)
        if not prompt_def:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=0,
                model_used="none",
                validation_status="FAILED",
                error=f"Prompt template '{request.prompt_id}' not found in registry."
            )

        # 3. Render Jinja2 Template
        try:
            rendered_prompt = Template(prompt_def.template).render(**request.variables)
        except Exception as e:
            return GenerationResponse(
                content="",
                usage=UsageStats(),
                latency_ms=0,
                model_used="none",
                validation_status="FAILED",
                error=f"Jinja2 Template Rendering Error: {str(e)}"
            )

        # 4. Generation & Auto-Repair Loop
        current_prompt = rendered_prompt
        total_usage = UsageStats()
        total_latency = 0
        validation_errors: List[str] = []
        retries_used = 0
        actual_max_retries = request.max_retries if request.max_retries is not None else self.max_retries

        for attempt in range(actual_max_retries + 1):
            response = await self.provider.generate(
                prompt=current_prompt,
                json_schema=prompt_def.schema_def,
                model_override=request.model_override,
                api_key_override=request.api_key_override
            )

            # Accumulate telemetry across attempts
            total_usage.prompt_tokens     += response.usage.prompt_tokens
            total_usage.completion_tokens += response.usage.completion_tokens
            total_usage.total_tokens      += response.usage.total_tokens
            total_usage.estimated_cost    += response.usage.estimated_cost
            total_latency                 += response.latency_ms

            # Check if LLM provider encountered fatal network/auth/quota error
            if response.error:
                return GenerationResponse(
                    content="",
                    usage=total_usage,
                    latency_ms=total_latency,
                    model_used=response.model_used,
                    validation_status="FAILED",
                    retry_count=attempt,
                    validation_errors=validation_errors,
                    error=response.error,
                    prompt_id=prompt_def.id,
                    prompt_version=prompt_def.version
                )

            # 5. Schema Validation
            if prompt_def.schema_def:
                is_valid, err_msg = OutputValidator.validate(
                    response.content, 
                    schema_def=prompt_def.schema_def
                )

                if is_valid:
                    status = "AUTO_REPAIRED" if attempt > 0 else "PASSED"
                    # Always ensure content is returned as parsed dict if valid JSON
                    out_content = response.content
                    if isinstance(out_content, str):
                        try:
                            out_content = json.loads(out_content.strip())
                        except Exception:
                            pass

                    final_result = GenerationResponse(
                        content=out_content,
                        usage=total_usage,
                        latency_ms=total_latency,
                        model_used=response.model_used,
                        validation_status=status,
                        retry_count=attempt,
                        validation_errors=validation_errors,
                        prompt_id=prompt_def.id,
                        prompt_version=prompt_def.version
                    )
                    Cache.set_cache(request.prompt_id, request.variables, request.task_type, final_result)
                    return final_result
                else:
                    validation_errors.append(f"Attempt {attempt + 1}: {err_msg}")
                    retries_used = attempt + 1
                    
                    # Construct smart auto-repair prompt
                    current_prompt = (
                        f"{rendered_prompt}\n\n"
                        f"[SYSTEM REPAIR FEEDBACK - ATTEMPT {attempt + 1} OF {actual_max_retries}]\n"
                        f"Your previous output failed JSON schema validation with this error:\n"
                        f"{err_msg}\n\n"
                        f"Previous invalid output:\n{response.content}\n\n"
                        f"Please carefully correct the JSON to strictly satisfy all schema requirements."
                    )
            else:
                # Raw text generation without schema
                final_result = GenerationResponse(
                    content=response.content,
                    usage=total_usage,
                    latency_ms=total_latency,
                    model_used=response.model_used,
                    validation_status="SKIPPED",
                    retry_count=0,
                    prompt_id=prompt_def.id,
                    prompt_version=prompt_def.version
                )
                Cache.set_cache(request.prompt_id, request.variables, request.task_type, final_result)
                return final_result

        # If retries exhausted without passing validation
        return GenerationResponse(
            content=response.content,
            usage=total_usage,
            latency_ms=total_latency,
            model_used=response.model_used,
            validation_status="FAILED",
            retry_count=retries_used,
            validation_errors=validation_errors,
            error=f"Validation failed after {retries_used} auto-repair retries. Last error: {validation_errors[-1] if validation_errors else 'Unknown'}",
            prompt_id=prompt_def.id,
            prompt_version=prompt_def.version
        )
