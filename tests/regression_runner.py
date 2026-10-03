import asyncio
import time
from app.services.registry import PromptRegistry
from app.services.generation import GenerationService
from app.services.router import ModelRouter
from app.models.schemas import GenerationRequest

async def run_regression():
    print("Starting Prompt Regression Runner...")
    registry = PromptRegistry("registry.db")
    router = ModelRouter()
    
    # Ensure a prompt exists
    prompt = registry.get_prompt("extract_event")
    if not prompt:
        registry.add_prompt(
            name="extract_event",
            template="Extract the event details from: {{ text }}",
            schema_def={"type": "object", "properties": {"title": {"type": "string"}}}
        )
        
    provider = router.route("mock")
    service = GenerationService(provider, registry)
    
    test_cases = [f"Event dataset {i}" for i in range(50)]
    
    successes = 0
    total_latency = 0
    total_tokens = 0
    
    start_time = time.time()
    
    print(f"Running {len(test_cases)} validation cases against mock provider...")
    for text in test_cases:
        req = GenerationRequest(prompt_id="extract_event", variables={"text": text}, task_type="mock")
        res = await service.generate(req)
        if not res.error:
            successes += 1
            total_latency += res.latency_ms
            total_tokens += res.usage.total_tokens
            
    wall_time = time.time() - start_time
    
    print("\n=== Regression Report ===")
    print(f"Total Cases: {len(test_cases)}")
    print(f"Schema-Validity Rate: {(successes/len(test_cases))*100:.1f}%")
    print(f"Average Latency: {total_latency/len(test_cases):.1f} ms")
    print(f"Total Tokens Consumed: {total_tokens}")
    print(f"Wall Time: {wall_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(run_regression())
