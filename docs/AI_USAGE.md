# AI Usage & Verification Log

As required by the one-month challenge, this document outlines how AI tools were utilized during the development of this platform and how the generated code was verified.

## 1. Ideation & Architecture
AI was used to brainstorm the initial architecture layout, specifically regarding how to implement the "Auto-Repair Loop" for JSON schema validation.
*   **Verification:** The resulting architecture was cross-referenced against the challenge's "Core Requirements" to ensure the core logic (provider adapter, registry, repair loop) was hand-written and not just wrapping an external SaaS API.

## 2. Scaffolding & Boilerplate
AI (Google Gemini/Antigravity) was used to generate standard boilerplate code:
*   Pydantic schema definitions (`app/models/schemas.py`).
*   FastAPI route wiring (`app/main.py`).
*   The Streamlit UI layout (`app/ui.py`).
*   **Verification:** Code was manually reviewed to ensure it adhered to local project paths. Pydantic models were tested to ensure strict typing for tokens and latency fields.

## 3. Core Logic (Human-Guided)
The following files were heavily directed by explicit human requirements and verified via automated testing:
*   `app/services/generation.py`: The retry loop logic was carefully constructed to aggregate latency and tokens across multiple attempts, rather than just returning the final attempt's metrics.
*   `app/services/registry.py`: The SQLite auto-incrementing version logic was tested to ensure prompts are immutable.

## 4. Test Generation
AI was used to generate initial `pytest` cases for the registry and schema validator.
*   **Verification:** Tests were executed locally (`pytest tests/`) to guarantee the deterministic `MockLLM` behaved exactly as expected without making network calls.
