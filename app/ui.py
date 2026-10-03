import streamlit as st
import requests
import json
import sqlite3
import pandas as pd
import asyncio
import os
import sys

# Add project root to sys.path so imports work seamlessly on Streamlit Cloud
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app.models.schemas import GenerationRequest
from app.services.registry import PromptRegistry
from app.services.generation import GenerationService
from app.services.router import ModelRouter

API_URL = "http://localhost:8000"

st.set_page_config(page_title="PromptOps", page_icon="🧪", layout="centered")

# ── INITIALIZE LOCAL IN-PROCESS ENGINE ─────────────────────
# This guarantees that the app works 100% on Streamlit Cloud without needing an external FastAPI server
registry = PromptRegistry("registry.db")

# Seed default prompts if database is newly initialized
if not registry.get_prompt("extract_event"):
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

def execute_generation(prompt_id: str, variables: dict, task_type: str, max_retries: int = 2, stream: bool = False):
    """
    Executes generation through FastAPI if available, otherwise falls back
    to in-process execution so Streamlit Cloud works seamlessly!
    """
    # 1. Try FastAPI backend if running locally
    try:
        res = requests.post(
            f"{API_URL}/generate",
            json={
                "prompt_id": prompt_id,
                "variables": variables,
                "task_type": task_type,
                "stream": stream
            },
            timeout=3
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass

    # 2. In-Process Engine execution (for Streamlit Cloud or standalone)
    provider = router.route(task_type or "mock")
    service = GenerationService(provider=provider, registry=registry, max_retries=max_retries)
    req = GenerationRequest(
        prompt_id=prompt_id,
        variables=variables,
        task_type=task_type,
        stream=stream
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        response = loop.run_until_complete(service.generate(req))
        return response.model_dump() if hasattr(response, "model_dump") else response.dict()
    finally:
        loop.close()

def save_new_prompt(name: str, template: str, description: str, schema_def: dict):
    """Saves prompt either via FastAPI or in-process."""
    try:
        res = requests.post(
            f"{API_URL}/registry/add",
            json={
                "name": name,
                "template": template,
                "description": description,
                "schema_def": schema_def
            },
            timeout=3
        )
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass

    saved = registry.add_prompt(
        name=name,
        template=template,
        description=description,
        schema_def=schema_def
    )
    return saved.model_dump() if hasattr(saved, "model_dump") else saved.dict()


# ── SIDEBAR ────────────────────────────────────────────────
with st.sidebar:

    # 🔌 Backend Status
    st.header("🔌 Engine Status")
    api_online = False
    try:
        health = requests.get(f"{API_URL}/health", timeout=1)
        if health.status_code == 200:
            api_online = True
    except Exception:
        api_online = False

    if api_online:
        st.success("✅ FastAPI Backend Connected (Port 8000)")
    else:
        st.info("☁️ Cloud Standalone Engine (Active)")

    st.divider()

    # ⚙️ Configuration
    st.header("⚙️ Configuration")
    prompt_id = st.text_input(
        "Prompt ID",
        value="extract_event_v1",
        help="Name + version of the prompt template (e.g. extract_event_v1)"
    )
    task_route = st.selectbox(
        "Model Route",
        ["mock", "extraction", "complex_reasoning"],
        help="mock = deterministic test | extraction = fast model | complex_reasoning = quality model"
    )
    enable_stream = st.toggle(
        "Stream Output",
        value=False,
        help="Enable token-by-token streaming (text output only)"
    )
    max_retries = st.slider(
        "Max Repair Retries",
        min_value=1, max_value=5, value=2,
        help="How many times the system will retry if JSON validation fails"
    )

    st.divider()

    # ➕ Add New Prompt
    st.header("➕ Add New Prompt")
    with st.form("add_prompt_form", clear_on_submit=True):
        new_name     = st.text_input("Prompt Name", placeholder="e.g. summarize_meeting")
        new_template = st.text_area(
            "Template (Jinja2)",
            placeholder='Summarize this meeting: {{ text }}',
            height=80
        )
        new_desc   = st.text_input("Description", placeholder="Short description")
        new_schema = st.text_area(
            "Output Schema (JSON)",
            placeholder='{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
            height=80
        )
        submitted = st.form_submit_button("💾 Save to Registry")

        if submitted:
            if not new_name or not new_template:
                st.warning("⚠️ Prompt Name and Template are required.")
            else:
                try:
                    schema_def = json.loads(new_schema) if new_schema.strip() else None
                    saved = save_new_prompt(new_name, new_template, new_desc, schema_def)
                    st.success(f"✅ Saved as `{saved.get('id')}`")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("❌ Invalid JSON in Output Schema field.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

    st.divider()

    # 📚 Prompt Registry Table
    st.header("📚 Prompt Registry")
    try:
        conn = sqlite3.connect("registry.db")
        df = pd.read_sql_query("SELECT id, name, version, description FROM prompts", conn)
        conn.close()
        if not df.empty:
            st.dataframe(df, hide_index=True)
        else:
            st.info("No prompts yet. Add one above!")
    except Exception:
        st.warning("Registry unavailable.")


# ── MAIN AREA ──────────────────────────────────────────────
st.title("🧪 PromptOps Platform")
st.caption("Convert messy instructions into validated structured outputs.")
st.divider()

st.subheader("📝 Input")
variables_input = st.text_area(
    "Variables (JSON)",
    value='{\n  "text": "Product launch event next Friday at 3 PM."\n}',
    height=120,
    help="JSON variables to inject into the selected prompt template."
)

run_btn = st.button("▶ Run Generation", type="primary")

if run_btn:
    try:
        variables = json.loads(variables_input)
    except json.JSONDecodeError:
        st.error("❌ Invalid JSON. Please fix the Variables field.")
        st.stop()

    with st.spinner("Generating and validating output..."):
        try:
            data = execute_generation(
                prompt_id=prompt_id,
                variables=variables,
                task_type=task_route,
                max_retries=max_retries,
                stream=enable_stream
            )
        except Exception as e:
            st.error(f"❌ Execution error: {str(e)}")
            st.stop()

    st.divider()

    if data.get("error"):
        st.error(f"❌ Generation Failed: {data['error']}")
    else:
        st.success("✅ Generation Successful — Schema Valid")
        if data.get("cached"):
            st.info("⚡ Served from cache")

        st.subheader("📤 Output")
        content = data.get("content", {})
        if isinstance(content, dict):
            st.json(content)
        else:
            st.write(content)

        st.subheader("📊 Telemetry")
        usage = data.get("usage", {})
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("⏱ Latency",   f"{data.get('latency_ms', 0)} ms")
        col2.metric("🤖 Model",     data.get("model_used", "—"))
        col3.metric("🔢 Tokens",    usage.get("total_tokens", 0))
        col4.metric("💰 Est. Cost", f"${usage.get('estimated_cost', 0):.4f}")

# ── A/B COMPARE ────────────────────────────────────────────
st.divider()
with st.expander("⚖️ Compare Two Configurations"):
    st.caption("Run the same input against two different models or prompt versions side by side.")

    cmp_vars_input = st.text_area(
        "Variables (JSON)",
        value='{\n  "text": "Annual product summit on December 5th at 9 AM in Hall A."\n}',
        height=100,
        key="cmp_vars",
        help="Variables shared across both configurations."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Configuration A**")
        prompt_a = st.text_input("Prompt ID A", value="extract_event_v1", key="cmp_a")
        route_a  = st.selectbox("Route A", ["mock", "extraction", "complex_reasoning"], key="route_a")
    with col_b:
        st.markdown("**Configuration B**")
        prompt_b = st.text_input("Prompt ID B", value="extract_event_v2", key="cmp_b")
        route_b  = st.selectbox("Route B", ["mock", "extraction", "complex_reasoning"], key="route_b")

    cmp_btn = st.button("⚖️ Run Comparison", key="cmp_btn")

    if cmp_btn:
        try:
            cmp_variables = json.loads(cmp_vars_input)
        except json.JSONDecodeError:
            st.error("❌ Invalid JSON in Variables field.")
            st.stop()

        with st.spinner("Running Configuration A & B..."):
            try:
                res_a = execute_generation(
                    prompt_id=prompt_a,
                    variables=cmp_variables,
                    task_type=route_a,
                    max_retries=max_retries
                )
                res_b = execute_generation(
                    prompt_id=prompt_b,
                    variables=cmp_variables,
                    task_type=route_b,
                    max_retries=max_retries
                )
            except Exception as e:
                st.error(f"❌ Comparison error: {str(e)}")
                st.stop()

        # Results displayed OUTSIDE spinner blocks
        st.divider()
        st.subheader("📊 Comparison Results")
        out_a, out_b = st.columns(2)

        with out_a:
            st.markdown(f"**Config A — `{prompt_a}` / `{route_a}`**")
            if res_a.get("error"):
                st.error(f"❌ Failed: {res_a['error']}")
            else:
                st.success("✅ Success")
                content_a = res_a.get("content", {})
                st.json(content_a) if isinstance(content_a, dict) else st.write(content_a)
                usage_a = res_a.get("usage", {})
                st.metric("⏱ Latency", f"{res_a.get('latency_ms', 0)} ms")
                st.metric("🤖 Model",   res_a.get("model_used", "—"))
                st.metric("🔢 Tokens",  usage_a.get("total_tokens", 0))
                st.metric("💰 Cost",    f"${usage_a.get('estimated_cost', 0):.4f}")
                if res_a.get("cached"):
                    st.info("⚡ Cached")

        with out_b:
            st.markdown(f"**Config B — `{prompt_b}` / `{route_b}`**")
            if res_b.get("error"):
                st.error(f"❌ Failed: {res_b['error']}")
            else:
                st.success("✅ Success")
                content_b = res_b.get("content", {})
                st.json(content_b) if isinstance(content_b, dict) else st.write(content_b)
                usage_b = res_b.get("usage", {})
                st.metric("⏱ Latency", f"{res_b.get('latency_ms', 0)} ms")
                st.metric("🤖 Model",   res_b.get("model_used", "—"))
                st.metric("🔢 Tokens",  usage_b.get("total_tokens", 0))
                st.metric("💰 Cost",    f"${usage_b.get('estimated_cost', 0):.4f}")
                if res_b.get("cached"):
                    st.info("⚡ Cached")
