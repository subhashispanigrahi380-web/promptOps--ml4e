# PromptOps Architecture & Design Decisions

This document justifies the architectural choices made for the PromptOps platform to satisfy the core requirements of the one-month challenge.

## 1. Fast API (Backend Core)
**Decision:** Use FastAPI for the core routing and API layer.
**Justification:** The system must support asynchronous execution and streaming text. FastAPI is natively async (ASGI) and handles high-concurrency requests efficiently. Its integration with Pydantic makes request/response validation strict and self-documenting.

## 2. LiteLLM (Provider Agnostic Layer)
**Decision:** Use `litellm` as the provider adapter layer instead of direct OpenAI/Anthropic SDKs.
**Justification:** The challenge requires a provider-agnostic platform supporting at least two backends. LiteLLM standardizes inputs and outputs across 100+ LLMs, automatically calculating token costs and standardizing error handling. It allows our routing logic (`app/services/router.py`) to swap models seamlessly without changing the core generation logic.

## 3. SQLite + Jinja2 (Prompt Registry)
**Decision:** Store prompts in a local SQLite database and render them using Jinja2.
**Justification:** 
*   **Immutability & Versioning:** Every prompt edit generates a new version (e.g., `_v1`, `_v2`). This makes prompt regression testing reliable.
*   **Jinja2:** Standardizes variable injection, allowing complex conditional logic inside prompts if needed.
*   **SQLite:** Zero-dependency database, making the platform easy to deploy and test locally.

## 4. JSON Schema Validation & Auto-Repair Loop
**Decision:** Enforce structural integrity using the `jsonschema` library and implement an automatic retry loop.
**Justification:** LLMs (especially smaller/faster ones) frequently hallucinate JSON structures. Instead of failing immediately, the `GenerationService` intercepts schema validation errors and appends them to the prompt, giving the model a chance to "repair" its own output before returning a final failure. This satisfies the requirement to "survive model failures".

## 5. Streamlit (Experiment UI)
**Decision:** Build the frontend using Streamlit.
**Justification:** The challenge requires an "experiment UI to compare prompt and model versions side by side." Streamlit allows us to build a highly interactive, python-native dashboard rapidly. The side-by-side layout lets engineers visually verify how a prompt change or model swap affects output quality and latency.
