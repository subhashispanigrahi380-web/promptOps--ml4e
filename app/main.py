from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from app.models.schemas import GenerationRequest, GenerationResponse
from app.services.registry import PromptRegistry, PromptVersion
from app.services.generation import GenerationService
from app.services.router import ModelRouter
from app.services.evaluator import PromptEvaluator
from app.services import cache as Cache
import uvicorn

app = FastAPI(
    title="PromptOps Production API",
    description="Provider-agnostic platform converting messy instructions into reliable, validated structured outputs.",
    version="2.0.0"
)

registry = PromptRegistry()
router = ModelRouter()
evaluator = PromptEvaluator(registry=registry, router=router)

class AddPromptRequest(BaseModel):
    name: str
    template: str
    description: Optional[str] = ""
    schema_def: Optional[Dict[str, Any]] = None

class EvaluateRequest(BaseModel):
    prompt_id: str
    provider_name: str = "gemini"
    model_override: Optional[str] = None
    api_key_override: Optional[str] = None

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PromptOps Production Platform",
        "cache": Cache.cache_stats(),
        "available_providers": ["gemini", "groq", "openai", "mock"]
    }

@app.post("/generate", response_model=GenerationResponse)
async def generate_text(request: GenerationRequest):
    provider = router.route(request.task_type or "gemini", request.api_key_override)
    service  = GenerationService(provider=provider, registry=registry, max_retries=request.max_retries)
    return await service.generate(request)

@app.post("/generate/stream")
async def generate_stream(request: GenerationRequest):
    """Token-by-token streaming endpoint."""
    provider = router.route(request.task_type or "gemini", request.api_key_override)

    async def token_generator():
        async for chunk in provider.generate_stream(
            prompt=request.prompt_id,
            model_override=request.model_override,
            api_key_override=request.api_key_override
        ):
            yield chunk

    return StreamingResponse(token_generator(), media_type="text/plain")

@app.post("/registry/add", response_model=PromptVersion)
def add_prompt(request: AddPromptRequest):
    return registry.add_prompt(
        name=request.name,
        template=request.template,
        description=request.description,
        schema_def=request.schema_def
    )

@app.get("/registry/list")
def list_prompts():
    prompts = registry.list_all_prompts()
    return [p.model_dump() if hasattr(p, "model_dump") else p.dict() for p in prompts]

@app.post("/evaluate")
async def evaluate_prompt(request: EvaluateRequest):
    return await evaluator.run_evaluation(
        prompt_id=request.prompt_id,
        provider_name=request.provider_name,
        model_override=request.model_override,
        api_key_override=request.api_key_override
    )

@app.get("/evaluations/history")
def get_evaluations(limit: int = 20):
    return registry.get_evaluation_history(limit=limit)

@app.get("/cache/stats")
def get_cache_stats():
    return Cache.cache_stats()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
