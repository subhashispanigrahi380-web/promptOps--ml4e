import json
import time
from typing import Dict, Any, List, Optional
from app.models.schemas import GenerationRequest, EvaluationRecord
from app.services.generation import GenerationService
from app.services.registry import PromptRegistry
from app.services.router import ModelRouter

# Built-in benchmark test cases for the 5 core domains
BENCHMARK_SUITES: Dict[str, List[Dict[str, Any]]] = {
    "event_extraction": [
        {
            "name": "Tech Conference Announcement",
            "variables": {"text": "Join us for PyData Global 2026 on November 14th from 9:00 AM to 5:00 PM at Moscone Center, San Francisco. Keynotes by Guido van Rossum and Wes McKinney."},
            "required_keys": ["title", "date", "location"]
        },
        {
            "name": "Virtual Team All-Hands",
            "variables": {"text": "Q4 Engineering All-Hands scheduled for next Tuesday, Oct 20 at 2 PM UTC on Zoom. Host: Sarah Connor."},
            "required_keys": ["title", "date"]
        },
        {
            "name": "Product Launch Gala",
            "variables": {"text": "PromptOps 2.0 Launch Party on Friday December 18 at 7 PM EST. Venue: Rooftop Lounge NYC. RSVP required."},
            "required_keys": ["title", "date", "time"]
        }
    ],
    "contact_extraction": [
        {
            "name": "Corporate Email Signature",
            "variables": {"text": "Best regards,\nElena Rostova | VP of AI Infrastructure\nNexus Corp\nDirect: +1 (415) 890-1234 | elena.r@nexuscorp.io\nLinkedIn: linkedin.com/in/erostova"},
            "required_keys": ["full_name", "email", "organization"]
        },
        {
            "name": "Conference Badge Info",
            "variables": {"text": "Dr. Marcus Chen - Chief Scientist at QuantumBio. Contact via marcus@quantumbio.org or cell: 555-0199."},
            "required_keys": ["full_name", "organization"]
        },
        {
            "name": "Informal Bio Note",
            "variables": {"text": "Reach out to Chloe Bennett (Freelance Designer). Email: chloe@designs.co, portfolio: https://chloedesigns.com"},
            "required_keys": ["full_name", "email"]
        }
    ],
    "meeting_summary": [
        {
            "name": "Sprint Planning Meeting",
            "variables": {"transcript": "Meeting on Oct 12: Team reviewed sprint velocity. Decided to adopt Gemini 1.5 as default model. Action items: Alex to update router by Wednesday, Priya to write 20 new tests by Friday."},
            "required_keys": ["meeting_title", "action_items", "decisions_made"]
        },
        {
            "name": "Client Budget Review",
            "variables": {"transcript": "Quarterly Budget Sync: Agreed to cap inference budget at $2,000/month. Bob will configure CloudWatch alerts by tomorrow."},
            "required_keys": ["key_discussion_points", "action_items"]
        }
    ],
    "task_extraction": [
        {
            "name": "Slack Bug Report Thread",
            "variables": {"notes": "Urgent: Payment webhook fails on 500 status (TASK-1, High, assigned to Dave, 3 hours). Also need to fix CSS button alignment (TASK-2, Low, assigned to Maya, 1 hour)."},
            "required_keys": ["project_name", "tasks"]
        },
        {
            "name": "Feature Backlog Grooming",
            "variables": {"notes": "Sprint 42: Implement JWT refresh tokens (TASK-101, High, John, 5h). Add CSV export button (TASK-102, Medium, Lisa, 2h)."},
            "required_keys": ["tasks"]
        }
    ],
    "job_parser": [
        {
            "name": "Senior Backend Engineer Post",
            "variables": {"job_post": "PromptOps Inc is hiring a Senior Backend Engineer in San Francisco (Hybrid/Full-time). Salary: $170k - $210k. Requirements: 5+ years Python, FastAPI, Docker, PostgreSQL, AsyncIO. You will architect high-throughput LLM pipelines."},
            "required_keys": ["job_title", "company", "required_skills"]
        },
        {
            "name": "Remote ML Ops Specialist",
            "variables": {"job_post": "OpenAI Partner seeking Remote MLOps Engineer (Contract). Requires Kubernetes, LiteLLM, PyTorch. Hourly: $90-$120/hr. Lead our model evaluation infrastructure."},
            "required_keys": ["job_title", "employment_type", "required_skills"]
        }
    ]
}

class PromptEvaluator:
    def __init__(self, registry: PromptRegistry, router: ModelRouter):
        self.registry = registry
        self.router = router

    async def run_evaluation(
        self,
        prompt_id: str,
        provider_name: str = "gemini",
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes benchmark test cases against the specified prompt and provider,
        computes pass/fail metrics, and logs the evaluation history to SQLite.
        """
        # Resolve benchmark suite based on prompt name
        base_name = prompt_id.rsplit('_v', 1)[0] if '_v' in prompt_id else prompt_id
        test_cases = BENCHMARK_SUITES.get(base_name)
        
        # If no specific suite found, fall back to event extraction cases
        if not test_cases:
            test_cases = BENCHMARK_SUITES["event_extraction"]

        provider = self.router.route(provider_name, api_key_override)
        service = GenerationService(provider=provider, registry=self.registry, max_retries=1)

        results_breakdown = []
        total_latency = 0
        total_tokens = 0
        total_cost = 0.0
        passed_count = 0

        for case in test_cases:
            start_t = time.time()
            req = GenerationRequest(
                prompt_id=prompt_id,
                variables=case["variables"],
                task_type=provider_name,
                model_override=model_override,
                api_key_override=api_key_override,
                max_retries=1
            )
            resp = await service.generate(req)
            dur_ms = int((time.time() - start_t) * 1000)

            # Check criteria
            is_valid_schema = resp.validation_status in ("PASSED", "AUTO_REPAIRED") and not resp.error
            has_required_keys = True
            if isinstance(resp.content, dict):
                for k in case.get("required_keys", []):
                    if k not in resp.content or not resp.content[k]:
                        has_required_keys = False
                        break
            else:
                has_required_keys = False

            passed = is_valid_schema and has_required_keys
            if passed:
                passed_count += 1

            total_latency += resp.latency_ms or dur_ms
            total_tokens += resp.usage.total_tokens
            total_cost += resp.usage.estimated_cost

            results_breakdown.append({
                "case_name": case["name"],
                "passed": passed,
                "validation_status": resp.validation_status,
                "latency_ms": resp.latency_ms or dur_ms,
                "tokens": resp.usage.total_tokens,
                "error": resp.error,
                "preview": resp.content if isinstance(resp.content, dict) else str(resp.content)[:100]
            })

        total_cases = len(test_cases)
        pass_rate = round((passed_count / total_cases) * 100, 1) if total_cases > 0 else 0.0
        avg_latency = round(total_latency / total_cases, 1) if total_cases > 0 else 0.0
        actual_model = results_breakdown[0].get("preview", {}).get("model") if results_breakdown else provider_name

        # Store in evaluation history
        self.registry.log_evaluation(
            prompt_id=prompt_id,
            model_used=model_override or provider_name,
            total_cases=total_cases,
            passed_cases=passed_count,
            pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            total_tokens=total_tokens,
            total_cost=round(total_cost, 6),
            breakdown_json=json.dumps(results_breakdown)
        )

        return {
            "prompt_id": prompt_id,
            "model_used": model_override or provider_name,
            "total_cases": total_cases,
            "passed_cases": passed_count,
            "pass_rate_pct": pass_rate,
            "avg_latency_ms": avg_latency,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "breakdown": results_breakdown
        }
