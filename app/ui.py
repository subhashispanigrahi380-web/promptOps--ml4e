import streamlit as st
import json
import sqlite3
import pandas as pd
import asyncio
import os
import sys

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app.models.schemas import GenerationRequest
from app.services.registry import PromptRegistry
from app.services.generation import GenerationService
from app.services.router import ModelRouter
from app.services.evaluator import PromptEvaluator
from app.services.providers.gemini_provider import get_gemini_key
from app.services.providers.openai_compatible import get_secret

# ── PAGE CONFIGURATION ──────────────────────────────────────
st.set_page_config(
    page_title="PromptOps | Controlled LLM Generation Platform",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── IN-PROCESS PLATFORM ENGINE INITIALIZATION ───────────────
@st.cache_resource
def get_registry():
    db_path = os.path.join(parent_dir, "registry.db")
    return PromptRegistry(db_path=db_path)

registry = get_registry()
router = ModelRouter()
evaluator = PromptEvaluator(registry=registry, router=router)

# ── PRESET SAMPLE DATA FOR THE 5 TEMPLATES ─────────────────
SAMPLE_INPUTS = {
    "event_extraction": json.dumps({
        "text": "Join us for PyData Global 2026 on November 14th from 9:00 AM to 5:00 PM at Moscone Center, San Francisco. Keynote speakers include Guido van Rossum and Wes McKinney. Register at pydata.org."
    }, indent=2),
    "contact_extraction": json.dumps({
        "text": "Best regards,\nElena Rostova | VP of AI Infrastructure\nNexus Systems\nDirect: +1 (415) 890-1234 | Email: elena.r@nexussystems.io\nLinkedIn: https://linkedin.com/in/erostova\nGitHub: https://github.com/erostova"
    }, indent=2),
    "meeting_summary": json.dumps({
        "transcript": "Meeting Date: Oct 12, 2026. Attendees: Alex, Priya, Marcus.\nReviewed sprint velocity. Marcus noted payment webhook latency. Decided to adopt Gemini 1.5 Flash as the default extraction engine for 10x cost reduction. Action items: Alex to update router by Wednesday, Priya to write 25 schema tests by Friday, Marcus to benchmark Groq throughput."
    }, indent=2),
    "task_extraction": json.dumps({
        "notes": "Sprint 44 Grooming Notes:\n1. Payment Gateway Bug: Webhook times out on 500 error (TASK-101, High priority, assigned to Dave, estimate 4 hours).\n2. CSS Polish: Align dark mode buttons in sidebar (TASK-102, Low priority, assigned to Maya, estimate 1.5 hours).\n3. Auth Refactor: Implement JWT refresh tokens (TASK-103, High priority, assigned to Sarah, estimate 6 hours)."
    }, indent=2),
    "job_parser": json.dumps({
        "job_post": "PromptOps Inc is hiring a Senior Backend AI Engineer in San Francisco, CA (Hybrid / Full-time). Salary: $165,000 - $210,000 + Equity. Requirements: 5+ years with Python, FastAPI, Docker, and AsyncIO. Experience with LLM orchestration (LiteLLM, LangChain, or vLLM) and prompt evaluation frameworks required. You will lead our high-throughput structured generation pipeline."
    }, indent=2)
}

# ── SIDEBAR: PROVIDER & API KEY CONTROLS ───────────────────
with st.sidebar:
    st.title("🧪 PromptOps Control")
    st.caption("Controlled Structured Generation & Evaluation")
    st.divider()

    # Engine Status Badge
    gemini_key_detected = bool(get_gemini_key())
    groq_key_detected = bool(get_secret("GROQ_API_KEY"))
    openai_key_detected = bool(get_secret("OPENAI_API_KEY"))

    st.subheader("🔑 Provider Status")
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        st.write("Gemini: " + ("🟢 Ready" if gemini_key_detected else "⚪ Missing"))
        st.write("Groq: " + ("🟢 Ready" if groq_key_detected else "⚪ Missing"))
    with col_k2:
        st.write("OpenAI: " + ("🟢 Ready" if openai_key_detected else "⚪ Missing"))
        st.write("Mock: 🟢 Active")

    with st.expander("⚙️ Enter / Override API Keys", expanded=not gemini_key_detected):
        st.caption("Keys are stored only in your session and never logged.")
        user_gemini_key = st.text_input("Gemini API Key", type="password", placeholder="AIzaSy...")
        user_groq_key = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        user_openai_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")

    st.divider()

    # Active Provider Route Selector
    st.subheader("🤖 Active LLM Route")
    provider_options = ["gemini", "gemini-pro", "groq", "groq-fast", "openai", "mock"]
    selected_provider = st.selectbox(
        "Default Inference Provider",
        provider_options,
        index=0 if (gemini_key_detected or user_gemini_key) else 5,
        help="Gemini uses google-generativeai / direct v1beta REST API with JSON mime mode."
    )

    max_repair_retries = st.slider(
        "Max Auto-Repair Retries",
        min_value=0, max_value=4, value=2,
        help="If generated JSON fails schema validation, the system feeds the validation error back to the model to repair."
    )

    enable_cache = st.toggle("Enable Response Caching", value=True)

# Helper function to resolve active API key
def resolve_api_key(provider_name: str) -> str:
    p = provider_name.lower()
    if "gemini" in p:
        return user_gemini_key or get_gemini_key() or ""
    elif "groq" in p:
        return user_groq_key or get_secret("GROQ_API_KEY") or ""
    elif "openai" in p:
        return user_openai_key or get_secret("OPENAI_API_KEY") or ""
    return ""

# Helper to execute generation in async event loop
def run_generation_sync(prompt_id: str, variables: dict, provider_name: str, max_retries: int):
    api_key = resolve_api_key(provider_name)
    provider = router.route(provider_name, api_key_override=api_key)
    service = GenerationService(provider=provider, registry=registry, max_retries=max_retries)
    
    req = GenerationRequest(
        prompt_id=prompt_id,
        variables=variables,
        task_type=provider_name,
        api_key_override=api_key,
        max_retries=max_retries
    )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(service.generate(req))
    finally:
        loop.close()

# ── MAIN TABS INTERFACE ─────────────────────────────────────
tab_gen, tab_compare, tab_eval, tab_registry = st.tabs([
    "⚡ Generation Playground",
    "⚖️ A/B Model & Version Comparison",
    "🧪 Prompt Evaluator & Benchmark",
    "📚 Prompt Registry & Versions"
])

# ==============================================================================
# TAB 1: GENERATION PLAYGROUND
# ==============================================================================
with tab_gen:
    st.header("⚡ Controlled Generation Playground")
    st.caption("Select a production prompt template, edit input variables, and execute structured schema-validated generation.")

    col_tmpl, col_ver = st.columns([3, 1])
    
    all_prompts = registry.list_all_prompts()
    prompt_names = list(dict.fromkeys([p.name for p in all_prompts]))

    with col_tmpl:
        selected_prompt_name = st.selectbox(
            "Select Prompt Template",
            prompt_names,
            index=0 if "event_extraction" in prompt_names else 0
        )

    # Get available versions for this template
    versions_for_name = [p for p in all_prompts if p.name == selected_prompt_name]
    with col_ver:
        selected_version_obj = st.selectbox(
            "Version",
            versions_for_name,
            format_func=lambda x: f"v{x.version} ({x.id})"
        )

    # Show template description and schema info
    if selected_version_obj:
        st.info(f"**Template Description:** {selected_version_obj.description or 'No description'}")

    # Variables input box
    st.subheader("📝 Input Variables (JSON)")
    default_sample = SAMPLE_INPUTS.get(selected_prompt_name, '{\n  "text": "Sample input text"\n}')
    
    variables_raw = st.text_area(
        "Jinja2 Template Variables",
        value=default_sample,
        height=140,
        help="Input JSON dictionary with keys matching Jinja2 variables in the template."
    )

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        generate_clicked = st.button("▶ Run Generation", type="primary", use_container_width=True)

    if generate_clicked:
        try:
            parsed_variables = json.loads(variables_raw)
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON in Variables field: {str(e)}")
            st.stop()

        with st.spinner(f"Running inference with {selected_provider.upper()} & validating schema..."):
            response = run_generation_sync(
                prompt_id=selected_version_obj.id,
                variables=parsed_variables,
                provider_name=selected_provider,
                max_retries=max_repair_retries
            )

        # Telemetry Display
        st.divider()
        st.subheader("📊 Execution Telemetry")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        
        status_color = "🟢" if response.validation_status == "PASSED" else ("🟡" if response.validation_status == "AUTO_REPAIRED" else "🔴")
        m1.metric("Validation", f"{status_color} {response.validation_status}")
        m2.metric("Latency", f"{response.latency_ms} ms")
        m3.metric("Tokens", f"{response.usage.total_tokens:,}")
        m4.metric("Est. Cost", f"${response.usage.estimated_cost:.5f}")
        m5.metric("Model", response.model_used)
        m6.metric("Retries", f"{response.retry_count}")

        if response.cached:
            st.success("⚡ Result served from in-memory cache (0 ms network overhead).")

        # Repair Log if retries occurred
        if response.validation_errors:
            with st.expander("🛠️ View Auto-Repair Feedback Log", expanded=False):
                for err in response.validation_errors:
                    st.warning(err)

        # Output Display
        st.subheader("📦 Structured JSON Output")
        if response.error:
            st.error(f"❌ Execution Failure: {response.error}")
            st.toast("Generation failed. Check API key or template variables.", icon="❌")
        else:
            json_str = json.dumps(response.content, indent=2)
            st.json(response.content)

            # Copy & Download Buttons
            c_down, c_toast = st.columns([2, 8])
            with c_down:
                st.download_button(
                    label="💾 Download JSON",
                    data=json_str,
                    file_name=f"{selected_version_obj.id}_output.json",
                    mime="application/json"
                )
            st.toast("Generation completed and schema validated!", icon="✅")

# ==============================================================================
# TAB 2: A/B MODEL & VERSION COMPARISON
# ==============================================================================
with tab_compare:
    st.header("⚖️ Side-by-Side Prompt & Model Comparator")
    st.caption("Evaluate how changes in prompt versioning or model provider impact latency, cost, and output quality.")

    cmp_input_raw = st.text_area(
        "Shared Test Variables (JSON)",
        value=SAMPLE_INPUTS.get("event_extraction", '{\n  "text": "Sample event"\n}'),
        height=100,
        key="ab_cmp_vars"
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### 🔹 Configuration A")
        cfg_a_prompt = st.selectbox("Prompt ID A", [p.id for p in all_prompts], index=0, key="cfg_a_p")
        cfg_a_model = st.selectbox("Model A", provider_options, index=0, key="cfg_a_m")

    with col_b:
        st.markdown("### 🔸 Configuration B")
        # Default Config B to version 2 if available
        def_idx = 1 if len(all_prompts) > 1 else 0
        cfg_b_prompt = st.selectbox("Prompt ID B", [p.id for p in all_prompts], index=def_idx, key="cfg_b_p")
        cfg_b_model = st.selectbox("Model B", provider_options, index=1 if len(provider_options) > 1 else 0, key="cfg_b_m")

    if st.button("⚖️ Run Side-by-Side Comparison", type="primary", use_container_width=True):
        try:
            cmp_vars = json.loads(cmp_input_raw)
        except json.JSONDecodeError as e:
            st.error(f"Invalid JSON: {str(e)}")
            st.stop()

        with st.spinner("Executing both configurations concurrently..."):
            res_a = run_generation_sync(cfg_a_prompt, cmp_vars, cfg_a_model, max_repair_retries)
            res_b = run_generation_sync(cfg_b_prompt, cmp_vars, cfg_b_model, max_repair_retries)

        st.divider()
        out_a, out_b = st.columns(2)

        with out_a:
            st.subheader(f"🔹 Config A ({cfg_a_prompt} / {cfg_a_model})")
            if res_a.error:
                st.error(res_a.error)
            else:
                st.json(res_a.content)
            
            st.markdown("**Telemetry A:**")
            st.write(f"⏱ Latency: **{res_a.latency_ms} ms** | 🔢 Tokens: **{res_a.usage.total_tokens}** | 💰 Cost: **${res_a.usage.estimated_cost:.5f}**")
            st.write(f"🛡️ Validation: **{res_a.validation_status}** | 🔄 Retries: **{res_a.retry_count}**")

        with out_b:
            st.subheader(f"🔸 Config B ({cfg_b_prompt} / {cfg_b_model})")
            if res_b.error:
                st.error(res_b.error)
            else:
                st.json(res_b.content)

            st.markdown("**Telemetry B:**")
            st.write(f"⏱ Latency: **{res_b.latency_ms} ms** | 🔢 Tokens: **{res_b.usage.total_tokens}** | 💰 Cost: **${res_b.usage.estimated_cost:.5f}**")
            st.write(f"🛡️ Validation: **{res_b.validation_status}** | 🔄 Retries: **{res_b.retry_count}**")

        st.toast("A/B comparison complete!", icon="⚖️")

# ==============================================================================
# TAB 3: PROMPT EVALUATOR & BENCHMARK
# ==============================================================================
with tab_eval:
    st.header("🧪 Prompt Benchmark & Quality Evaluator")
    st.caption("Stress-test prompt templates against multi-case test suites. Evaluates schema compliance, latency, and cost.")

    col_e1, col_e2, col_e3 = st.columns([2, 2, 1])
    with col_e1:
        eval_prompt_id = st.selectbox("Prompt Template to Benchmark", [p.id for p in all_prompts], key="eval_p_select")
    with col_e2:
        eval_provider = st.selectbox("Inference Model", provider_options, key="eval_prov_select")
    with col_e3:
        st.write("")
        st.write("")
        run_eval_btn = st.button("🚀 Run Benchmark", type="primary", use_container_width=True)

    if run_eval_btn:
        api_k = resolve_api_key(eval_provider)
        with st.spinner(f"Running automated benchmark test suite on {eval_prompt_id}..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                eval_summary = loop.run_until_complete(
                    evaluator.run_evaluation(
                        prompt_id=eval_prompt_id,
                        provider_name=eval_provider,
                        api_key_override=api_k
                    )
                )
            finally:
                loop.close()

        st.success(f"Benchmark completed for `{eval_prompt_id}`!")
        
        # Metric cards
        em1, em2, em3, em4 = st.columns(4)
        em1.metric("Pass Rate", f"{eval_summary['pass_rate_pct']}%", f"{eval_summary['passed_cases']}/{eval_summary['total_cases']} cases")
        em2.metric("Avg Latency", f"{eval_summary['avg_latency_ms']} ms")
        em3.metric("Total Tokens", f"{eval_summary['total_tokens']:,}")
        em4.metric("Benchmark Cost", f"${eval_summary['total_cost']:.5f}")

        # Breakdown table
        st.subheader("📋 Test Cases Breakdown")
        df_breakdown = pd.DataFrame(eval_summary["breakdown"])
        st.dataframe(df_breakdown, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📜 Historical Evaluation Log")
    eval_history = registry.get_evaluation_history(limit=10)
    if eval_history:
        df_hist = pd.DataFrame(eval_history)[["id", "prompt_id", "model_used", "total_cases", "passed_cases", "pass_rate_pct", "avg_latency_ms", "total_cost", "created_at"]]
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("No evaluation runs recorded yet. Click 'Run Benchmark' above.")

# ==============================================================================
# TAB 4: PROMPT REGISTRY & VERSIONS
# ==============================================================================
with tab_registry:
    st.header("📚 Versioned Prompt Registry")
    st.caption("All prompts are versioned immutably in SQLite with schemas and change history.")

    df_prompts = pd.DataFrame([
        {
            "Prompt ID": p.id,
            "Template Name": p.name,
            "Version": f"v{p.version}",
            "Description": p.description,
            "Has Schema": "✅ Yes" if p.schema_def else "❌ No"
        }
        for p in all_prompts
    ])
    st.dataframe(df_prompts, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("➕ Register New Prompt Version")
    with st.form("new_prompt_version_form", clear_on_submit=True):
        f_name = st.text_input("Prompt Name (e.g. invoice_parser, legal_analyzer)")
        f_desc = st.text_input("Version Description", placeholder="e.g. v1 - Added tax extraction")
        f_tmpl = st.text_area("Jinja2 Template", placeholder="Extract details from: {{ text }}", height=100)
        f_schema = st.text_area("JSON Schema (Optional)", placeholder='{"type": "object", "properties": {"title": {"type": "string"}}}', height=100)
        
        create_btn = st.form_submit_button("💾 Commit New Prompt Version", type="primary")
        if create_btn:
            if not f_name or not f_tmpl:
                st.warning("Prompt Name and Template are required.")
            else:
                try:
                    s_def = json.loads(f_schema) if f_schema.strip() else None
                    new_p = registry.add_prompt(name=f_name, template=f_tmpl, description=f_desc, schema_def=s_def)
                    st.success(f"Successfully registered **{new_p.id}**!")
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON Schema: {str(e)}")
