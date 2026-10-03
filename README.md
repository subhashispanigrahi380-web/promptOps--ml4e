# 🧪 PromptOps: Controlled LLM Generation & Evaluation Platform

A provider-agnostic, production-grade PromptOps platform that converts messy, unpredictable instructions into reliable, schema-validated structured outputs. Equipped with multi-model routing, automated repair feedback loops, prompt evaluation benchmarks, and full telemetry tracking.

---

## 🏗️ Architecture Overview

```
                                      +------------------------------------+
                                      |         Streamlit Cloud UI         |
                                      |     (Self-Contained & Cloud Native)|
                                      +-----------------+------------------+
                                                        |
                                                        v
                                          +----------------------------+
                                          |     GenerationService      |
                                          +-------------+--------------+
                                                        |
                 +-------------------+------------------+-------------------+-------------------+
                 |                   |                                      |                   |
                 v                   v                                      v                   v
        +-----------------+ +-----------------+                    +-----------------+ +-----------------+
        |  Cache Layer    | | PromptRegistry  |                    | ModelRouter     | | OutputValidator |
        |  (SHA-256 / TTL)| | (SQLite + Jinja)|                    | (Multi-Provider)| |(JSONSchema/Pyd) |
        +-----------------+ +-----------------+                    +--------+--------+ +-----------------+
                                                                            |
                                            +-------------------------------+-------------------------------+
                                            |                               |                               |
                                            v                               v                               v
                                   +-----------------+             +-----------------+             +-----------------+
                                   | GeminiProvider  |             |  GroqProvider   |             | OpenAIProvider  |
                                   | (gemini-1.5/2.0)|             | (llama-3.3-70b) |             | (gpt-4o / mini) |
                                   +-----------------+             +-----------------+             +-----------------+
                                            |
                                            v (Auto-Repair Loop if schema check fails)
                                   +-----------------+
                                   | Feedback Repair |
                                   +-----------------+
```

---

## ✨ Production Features

1. **Clean Provider Abstraction (`app/services/providers/`)**:
   - **Google Gemini**: Default provider via official Google v1beta API with native `application/json` structured response mode.
   - **Groq**: Ultra-fast low-latency inference using Llama 3.3 70B & Llama 3.1 8B.
   - **OpenAI**: GPT-4o and GPT-4o-mini with native JSON Object mode.
   - **Mock**: High-fidelity deterministic mock provider for CI testing, offline development, and zero-key evaluation.

2. **Pydantic Structured Outputs (`app/models/schemas.py`)**:
   - Strict typing, field descriptions, and JSON schema generation.
   - Automatic markdown fence stripping (` ```json ` cleaning).

3. **5 Production Prompt Templates**:
   - 📅 **Event Extraction (`event_extraction_v1`, `v2`)**: Extracts event title, date, time, venue, description, and attendees.
   - 📇 **Contact Extraction (`contact_extraction_v1`)**: Ingests email signatures and business cards into structured CRM contacts.
   - 📝 **Meeting Summary (`meeting_summary_v1`)**: Summarizes transcripts into key points, decisions, and action items with owners.
   - ✅ **Task Extraction (`task_extraction_v1`)**: Converts sprint chats/notes into prioritized tasks (TASK-1, estimated hours, assignee).
   - 💼 **Job Description Parser (`job_parser_v1`)**: Extracts role, compensation, skills, and responsibilities for ATS matching.

4. **Resilience & Auto-Repair Feedback Loop**:
   - Intercepts invalid JSON or schema violations.
   - Injects the exact validation error back into the model prompt and requests a targeted correction.
   - Retries up to $N$ attempts while aggregating total latency, token usage, and cost.

5. **Prompt Evaluation & Quality Benchmarks (`app/services/evaluator.py`)**:
   - Automated test harness running multi-case domain test suites.
   - Reports Pass Rate, Schema Compliance, Latency distribution, and Cost.
   - Persists evaluation history in SQLite.

6. **Comprehensive Telemetry**:
   - Real-time token tracking (Prompt, Completion, Total).
   - Live estimated cost per call using per-model pricing tables.
   - Millisecond-level latency profiling.
   - Validation status tags: `PASSED`, `AUTO_REPAIRED`, `FAILED`, `SKIPPED`.

7. **Streamlit Cloud Native**:
   - Fully operable standalone on Streamlit Cloud without running an external server.
   - Reads secrets from `st.secrets`, `.env`, or runtime user input.

---

## 🚀 Setup & Execution Guide

### 1. Local Environment Setup
```powershell
# Navigate to project
cd promptops

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Fill in your API keys (optional — Mock mode works out of the box with zero keys):
```ini
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...
```

### 3. Run the Platform

#### Option A: Streamlit UI (Recommended)
```powershell
streamlit run app/ui.py
```
Open **http://localhost:8501** in your browser.

#### Option B: Standalone FastAPI Backend
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation available at **http://localhost:8000/docs**.

#### Option C: Simultaneous Startup
```powershell
python run_all.py
```

---

## ☁️ Streamlit Cloud Deployment Guide

1. Push your repository to GitHub:
   ```bash
   git add .
   git commit -m "feat: production PromptOps upgrade"
   git push origin main
   ```
2. Log in to [share.streamlit.io](https://share.streamlit.io).
3. Select your repository `subhashispanigrahi380-web/promptOps--ml4e`.
4. Set Main file path: `app/ui.py`.
5. Under **Advanced Settings -> Secrets**, add your API keys:
   ```toml
   GEMINI_API_KEY = "your-gemini-api-key"
   GROQ_API_KEY = "your-groq-api-key"
   OPENAI_API_KEY = "your-openai-api-key"
   ```
6. Click **Deploy**! Your app will boot immediately and run in standalone cloud mode.

---

## 🧪 Automated Testing & Evidence

Run the full pytest suite (54 test cases covering validation, repair loops, timeouts, parameterization):
```powershell
pytest tests/ -v
```

Execute the 50-case repeatable benchmark regression runner:
```powershell
python tests/regression_runner.py
```

---

## 📁 Repository Structure

```
promptops/
├── app/
│   ├── main.py                  # FastAPI REST endpoints
│   ├── ui.py                    # Streamlit cloud-native interface (Playground, A/B, Evaluator, Registry)
│   ├── models/
│   │   └── schemas.py           # Domain schemas (Event, Contact, Meeting, Task, Job) + Telemetry
│   └── services/
│       ├── cache.py             # SHA-256 keyed cache with TTL
│       ├── evaluator.py         # Prompt evaluation suite and historical logger
│       ├── generation.py        # Orchestration, Jinja2 rendering, and auto-repair retry loop
│       ├── registry.py          # Versioned SQLite prompt registry seeded with 5 templates
│       ├── router.py            # Dynamic ModelRouter (Gemini, Groq, OpenAI, Mock)
│       ├── validator.py         # JSON Schema and Pydantic validator
│       └── providers/
│           ├── base.py          # Abstract LLMProvider interface & cost estimator
│           ├── gemini_provider.py # Direct Gemini API provider
│           ├── openai_compatible.py # Groq & OpenAI provider
│           └── mock_provider.py # High-fidelity deterministic mock provider
├── tests/
│   ├── test_core.py             # Unit tests for registry and validation
│   ├── test_generation.py       # 50+ test cases testing repair loops, timeouts, and schemas
│   └── regression_runner.py     # Repeatable 50-case benchmark runner
├── docs/
│   ├── ARCHITECTURE.md          # Architectural justification and design choices
│   ├── FAILURE_LOG.md           # Failure modes and mitigation catalog
│   └── AI_USAGE.md              # AI verification audit
├── pytest.ini                   # Asyncio test configuration
├── requirements.txt             # Production dependency list
├── .env.example                 # Environment variable template
└── run_all.py                   # Local dual-server launcher
```
