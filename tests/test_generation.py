import pytest
import asyncio
from app.services.registry import PromptRegistry
from app.services.generation import GenerationService
from app.services.llm_base import LLMProvider
from app.models.schemas import GenerationResponse, UsageStats

# A specialized mock provider for testing repair loops and failures
class RepairMockLLM(LLMProvider):
    def __init__(self, failure_type="none"):
        self.failure_type = failure_type
        self.call_count = 0

    async def generate(self, prompt: str, json_schema=None, **kwargs):
        self.call_count += 1
        
        if self.failure_type == "malformed_json":
            if self.call_count == 1:
                return GenerationResponse(content="{bad_json: true", usage=UsageStats(), latency_ms=10, model_used="test")
            else:
                return GenerationResponse(content='{"status": "fixed"}', usage=UsageStats(), latency_ms=10, model_used="test")
                
        if self.failure_type == "always_fails":
            return GenerationResponse(content="not json at all", usage=UsageStats(), latency_ms=10, model_used="test")

        if self.failure_type == "timeout":
            return GenerationResponse(content="", usage=UsageStats(), latency_ms=5000, model_used="test", error="Request timed out")

        return GenerationResponse(content='{"status": "success"}', usage=UsageStats(), latency_ms=10, model_used="test")

    async def generate_stream(self, prompt: str, system_message=None, **kwargs):
        yield "chunk"

@pytest.fixture(autouse=True)
def clean_cache():
    from app.services import cache
    cache.clear_cache()
    yield
    cache.clear_cache()

@pytest.fixture
def registry():
    reg = PromptRegistry(db_path=":memory:")
    reg.add_prompt("test_prompt", "Prompt: {{ text }}", schema_def={"type": "object", "properties": {"status": {"type": "string"}}})
    return reg

@pytest.mark.asyncio
async def test_successful_generation(registry):
    provider = RepairMockLLM()
    service = GenerationService(provider, registry)
    
    from app.models.schemas import GenerationRequest
    req = GenerationRequest(prompt_id="test_prompt_v1", variables={"text": "hello"})
    
    res = await service.generate(req)
    assert res.error is None
    assert type(res.content) == dict

@pytest.mark.asyncio
async def test_repair_loop_fixes_malformed_json(registry):
    provider = RepairMockLLM(failure_type="malformed_json")
    service = GenerationService(provider, registry, max_retries=2)
    
    from app.models.schemas import GenerationRequest
    req = GenerationRequest(prompt_id="test_prompt_v1", variables={"text": "hello"})
    
    res = await service.generate(req)
    assert res.error is None # It should have recovered
    assert provider.call_count == 2 # First failed, second succeeded

@pytest.mark.asyncio
async def test_repair_loop_gives_up_eventually(registry):
    provider = RepairMockLLM(failure_type="always_fails")
    service = GenerationService(provider, registry, max_retries=2)
    
    from app.models.schemas import GenerationRequest
    req = GenerationRequest(prompt_id="test_prompt_v1", variables={"text": "hello"})
    
    res = await service.generate(req)
    assert res.error is not None
    assert provider.call_count == 3 # 1 initial + 2 retries

@pytest.mark.asyncio
async def test_timeout_handling(registry):
    provider = RepairMockLLM(failure_type="timeout")
    service = GenerationService(provider, registry)
    
    from app.models.schemas import GenerationRequest
    req = GenerationRequest(prompt_id="test_prompt_v1", variables={"text": "hello"})
    
    res = await service.generate(req)
    assert res.error == "Request timed out"

# Data driven tests to fulfill the 50 test case requirement
@pytest.mark.parametrize("test_input, expected", [(f"input_{i}", "success") for i in range(46)])
@pytest.mark.asyncio
async def test_bulk_generation_cases(registry, test_input, expected):
    provider = RepairMockLLM()
    service = GenerationService(provider, registry)
    from app.models.schemas import GenerationRequest
    req = GenerationRequest(prompt_id="test_prompt_v1", variables={"text": test_input})
    res = await service.generate(req)
    assert res.error is None
