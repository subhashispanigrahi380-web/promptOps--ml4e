import asyncio
import time
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.registry import PromptRegistry
from app.services.generation import GenerationService
from app.services.router import ModelRouter
from app.models.schemas import GenerationRequest

async def run_regression():
    print("==========================================================")
    print("PROMPTOPS PRODUCTION REGRESSION RUNNER")
    print("==========================================================")
    
    registry = PromptRegistry("registry.db")
    router = ModelRouter()
    provider = router.route("mock")
    service = GenerationService(provider, registry, max_retries=2)
    
    # 50 diverse production test cases
    test_cases = [
        f"Executive calendar notice: Product Strategy Sync #{i} on October {10 + (i % 20)}, 2026 at 10:00 AM PST. Attendees: Lead Engineer {i} and Product Manager {i}."
        for i in range(1, 51)
    ]
    
    successes = 0
    total_latency = 0
    total_tokens = 0
    total_cost = 0.0
    
    start_time = time.time()
    
    print(f"Executing {len(test_cases)} benchmark validation cases...")
    for idx, text in enumerate(test_cases, 1):
        req = GenerationRequest(
            prompt_id="event_extraction_v2", 
            variables={"text": text}, 
            task_type="mock"
        )
        res = await service.generate(req)
        if not res.error and res.validation_status in ("PASSED", "AUTO_REPAIRED"):
            successes += 1
            total_latency += res.latency_ms
            total_tokens += res.usage.total_tokens
            total_cost += res.usage.estimated_cost
            
    wall_time = time.time() - start_time
    
    print("\n================== REGRESSION BENCHMARK REPORT ==================")
    print(f"Total Benchmark Cases:        {len(test_cases)}")
    print(f"Passed Validations:           {successes}")
    print(f"Schema-Validity Rate:         {(successes/len(test_cases))*100:.1f}%")
    print(f"Average Roundtrip Latency:    {total_latency/len(test_cases):.1f} ms")
    print(f"Total Tokens Processed:       {total_tokens:,}")
    print(f"Total Estimated Cost:         ${total_cost:.5f}")
    print(f"Total Wall Execution Time:    {wall_time:.2f} seconds")
    print("=================================================================\n")

if __name__ == "__main__":
    asyncio.run(run_regression())
