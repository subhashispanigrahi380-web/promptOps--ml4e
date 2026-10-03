from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.models.schemas import GenerationRequest, GenerationResponse
from app.services.registry import PromptRegistry, PromptVersion
from app.services.generation import GenerationService
from app.services.router import ModelRouter
from app.services import cache as Cache
import uvicorn

app = FastAPI(
    title="PromptOps API",
    description="Provider-agnostic platform for controlled structured generation.",
    version="1.0.0"
)

# ── Startup: seed registry ─────────────────────────────────
registry = PromptRegistry()

if not registry.get_prompt("extract_event"):
    # Version 1 — basic extraction
    registry.add_prompt(
        name="extract_event",
        template="Extract the event details from the following text: {{ text }}",
        description="v1 - Simple event extraction",
        schema_def={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date":  {"type": "string"}
            },
            "required": ["title", "date"]
        }
    )
    # Version 2 — richer extraction with location + attendees
    registry.add_prompt(
        name="extract_event",
        template=(
            "You are an expert assistant. Extract structured event details "
            "from this text: {{ text }}\n"
            "Return title, date, location and attendees."
        ),
        description="v2 - Rich extraction with location and attendees",
        schema_def={
            "type": "object",
            "properties": {
                "title":     {"type": "string"},
                "date":      {"type": "string"},
                "location":  {"type": "string"},
                "attendees": {"type": "string"}
            },
            "required": ["title", "date", "location", "attendees"]
        }
    )

router = ModelRouter()

# ── Request model for adding prompts ───────────────────────
class AddPromptRequest(BaseModel):
    name: str
    template: str
    description: Optional[str] = ""
    schema_def: Optional[Dict[str, Any]] = None

# ── Routes ─────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "healthy", "cache": Cache.cache_stats()}

@app.post("/generate", response_model=GenerationResponse)
async def generate_text(request: GenerationRequest):
    provider = router.route(request.task_type or "mock")
    service  = GenerationService(provider=provider, registry=registry)
    return await service.generate(request)

@app.post("/generate/stream")
async def generate_stream(request: GenerationRequest):
    """Token-by-token streaming endpoint."""
    provider = router.route(request.task_type or "mock")

    async def token_generator():
        async for chunk in provider.generate_stream(prompt=request.prompt_id):
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
    import sqlite3, json
    conn = sqlite3.connect(registry.db_path)
    cur  = conn.cursor()
    cur.execute("SELECT id, name, version, template, description, schema_def FROM prompts")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "name": r[1], "version": r[2],
            "template": r[3], "description": r[4],
            "schema_def": json.loads(r[5]) if r[5] else None
        }
        for r in rows
    ]

@app.get("/cache/stats")
def get_cache_stats():
    return Cache.cache_stats()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
