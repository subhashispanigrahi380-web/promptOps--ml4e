# PromptOps Architecture & Design Decisions (Production v2.0)

This document details the architectural choices, provider abstractions, and resilience patterns powering the PromptOps platform.

---

## 1. Provider Abstraction Layer (`app/services/providers/`)

### Decision: Direct-Engine Abstract Base Class (`LLMProvider`)
Rather than coupling the system to a single vendor SDK, all inference passes through an asynchronous abstract base class:
- `generate(prompt, system_message, json_schema, model_override, api_key_override)`
- `generate_stream(...)`

### Implemented Backends:
1. **Google Gemini (`GeminiProvider`)**:
   - Primary default provider.
   - Utilizes Google's v1beta REST endpoints with `responseMimeType: "application/json"`.
   - Extracts accurate token counts from `usageMetadata` (prompt, candidate, total).
2. **Groq (`GroqProvider`)**:
   - OpenAI-compatible engine optimized for ultra-low latency (~500 tokens/sec) on Llama 3.3 70B & 3.1 8B.
3. **OpenAI (`OpenAIProvider`)**:
   - GPT-4o and GPT-4o-mini with native `json_object` enforcement.
4. **Mock Provider (`MockProvider`)**:
   - Deterministic, zero-dependency backend that inspects incoming JSON schemas and dynamically generates realistic mock data. Ensures 100% test reliability in CI/CD environments.

---

## 2. Structured Output Pipeline & Schema Enforcement

### Decision: Pydantic Domain Schemas + Dynamic JSON Schema
Every extraction domain is modeled as a strict Pydantic class:
- `EventOutput`: Title, date, time, location, description, attendees.
- `ContactOutput`: Full name, email, phone, organization, role, social links.
- `MeetingSummaryOutput`: Title, date, discussion points, decisions, action items.
- `TaskExtractionOutput`: Project name, task list with priority and estimated hours.
- `JobDescriptionOutput`: Title, company, location, skills, compensation, duties.

When registering a template, the schema is serialized via `model_json_schema()` and stored in SQLite. At inference time, the model is guided with schema requirements, and the raw output is validated via `OutputValidator` (`jsonschema`).

---

## 3. Resilience Engine: Automated Repair Feedback Loop

### The Problem:
LLMs occasionally hallucinate malformed JSON syntax, omit required keys, or wrap responses in markdown fences (` ```json `).

### The Solution:
`GenerationService` executes an automated repair loop:
1. Strips markdown fences if present.
2. Validates JSON syntax and schema compliance.
3. If validation fails and retry budget remains:
   - Constructs an explicit feedback prompt containing the exact validator error message and the model's invalid output.
   - Instructs the model to perform a surgical fix.
4. Telemetry (latency, prompt tokens, completion tokens, cost) is aggregated across all repair attempts.
5. If retries are exhausted, a graceful `GenerationResponse` is returned with `validation_status="FAILED"` and complete error history.

---

## 4. Prompt Registry & Versioning (`app/services/registry.py`)

- **Database**: SQLite with connection-pooling and shared memory support.
- **Immutability**: Calling `add_prompt(name=...)` with an existing name automatically increments the version counter (`v1 -> v2 -> v3`), preserving historical prompt templates and schemas.
- **Templating**: Jinja2 templating allows clean variable interpolation.

---

## 5. Evaluation & Benchmarking Harness (`app/services/evaluator.py`)

To satisfy repeatable prompt regression testing:
- Houses domain-specific benchmark test suites.
- Executes batches against target prompts and models.
- Calculates:
  - **Pass Rate %**: Schema compliance + required key verification.
  - **Latency Profiling**: Average roundtrip execution time.
  - **Financial Cost**: Aggregated dollar cost based on token pricing table.
- Logs every evaluation run into an SQLite `evaluations` audit table for historical tracking.

---

## 6. Hybrid Cloud Architecture (Streamlit Cloud Native)

### The Problem:
Streamlit Community Cloud does not run background FastAPI daemon processes (`localhost:8000`).

### The Solution:
`app/ui.py` employs a hybrid execution pattern:
- It checks if a local FastAPI server is listening on port 8000.
- If unavailable (such as on Streamlit Cloud), it runs the `GenerationService`, `ModelRouter`, and `PromptRegistry` **directly in-process** using Python's asyncio loop.
- Result: **Zero external server required on Streamlit Cloud**. The app functions 100% out of the box with zero configuration.
