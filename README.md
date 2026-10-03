# PromptOps Platform

A **provider-agnostic controlled generation platform** that converts messy natural language instructions into reliable, validated, structured outputs — with caching, retries, routing, and a full experiment UI.

## Architecture Overview

```
User / UI
    │
    ▼
FastAPI Backend (app/main.py)
    │
    ├── ModelRouter ──► MockLLM | LiteLLM (GPT-3.5 / GPT-4o)
    │
    ├── PromptRegistry (SQLite + Jinja2 versioned templates)
    │
    ├── GenerationService
    │     ├── Cache Layer (SHA256 keyed, 5-min TTL)
    │     ├── Validation (jsonschema)
    │     └── Auto-Repair Loop (up to N retries)
    │
    └── Streaming Endpoint (/generate/stream)

Streamlit UI (app/ui.py)
    ├── Playground (Run + Telemetry)
    ├── A/B Comparison
    └── Prompt Registry Viewer + Add Form
```

## Quick Start

```bash
# 1. Clone and enter the project
cd promptops

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment (optional — needed for real LLM providers)
copy .env.example .env
# Edit .env and add your API keys

# 5. Start the platform
python run_all.py
```

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| FastAPI Docs | http://localhost:8000/docs |

## Run Tests

```bash
# All unit tests
pytest tests/ -v

# Regression report (50 cases)
python tests/regression_runner.py
```

## Deployment (Docker)

```bash
docker-compose up --build
```

## Project Structure

```
promptops/
├── app/
│   ├── main.py                  # FastAPI entrypoint
│   ├── ui.py                    # Streamlit frontend
│   ├── models/
│   │   └── schemas.py           # Pydantic models
│   └── services/
│       ├── llm_base.py          # Abstract provider interface
│       ├── mock_llm.py          # Deterministic mock backend
│       ├── litellm_provider.py  # Real LLM backend (LiteLLM)
│       ├── router.py            # Task-type routing logic
│       ├── registry.py          # Versioned prompt registry
│       ├── generation.py        # Orchestration + repair loop
│       ├── validator.py         # JSON schema validator
│       └── cache.py             # In-memory response cache
├── tests/
│   ├── test_core.py             # Registry + validator tests
│   ├── test_generation.py       # Generation + repair loop tests
│   └── regression_runner.py     # 50-case regression report
├── docs/
│   ├── ARCHITECTURE.md          # Design decisions
│   ├── FAILURE_LOG.md           # Known failure modes
│   └── AI_USAGE.md              # AI tool usage log
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
├── .env.example
└── run_all.py
```

## Core Requirements Coverage

| Requirement | Implementation |
|---|---|
| Common model interface | `app/services/llm_base.py` |
| Two backends | `mock_llm.py` + `litellm_provider.py` |
| Streaming output | `/generate/stream` endpoint |
| Versioned prompt registry | `registry.py` + SQLite |
| JSON schema validation | `validator.py` (jsonschema) |
| Repair + retry | `generation.py` repair loop |
| Caching | `cache.py` (SHA256 + TTL) |
| Token + latency + cost tracking | `UsageStats` in every response |
| Routing by task type | `router.py` |
| Experiment UI | `ui.py` (Streamlit) |
