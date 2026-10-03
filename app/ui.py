import streamlit as st
import requests
import json
import sqlite3
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="PromptOps", page_icon="🧪", layout="centered")

# ── SIDEBAR ────────────────────────────────────────────────
with st.sidebar:

    # 🔌 Backend Status
    st.header("🔌 Backend Status")
    try:
        health = requests.get(f"{API_URL}/health", timeout=2)
        if health.status_code == 200:
            st.success("✅ API is Online")
        else:
            st.error("❌ API returned an error")
    except Exception:
        st.error("❌ API Offline — run `python run_all.py`")

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
        new_name = st.text_input("Prompt Name", placeholder="e.g. summarize_meeting")
        new_template = st.text_area(
            "Template (Jinja2)",
            placeholder='Summarize this meeting: {{ text }}',
            height=80
        )
        new_desc = st.text_input("Description", placeholder="Short description of what this prompt does")
        new_schema = st.text_area(
            "Output Schema (JSON)",
            placeholder='{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
            height=80
        )
        submitted = st.form_submit_button("💾 Save to Registry", use_container_width=True)

        if submitted:
            if not new_name or not new_template:
                st.warning("⚠️ Prompt Name and Template are required.")
            else:
                try:
                    schema_def = json.loads(new_schema) if new_schema.strip() else None
                    # Call the registry API endpoint
                    payload = {
                        "name": new_name,
                        "template": new_template,
                        "description": new_desc,
                        "schema_def": schema_def
                    }
                    res = requests.post(f"{API_URL}/registry/add", json=payload, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        st.success(f"✅ Saved as `{data.get('id')}`")
                    else:
                        st.error(f"❌ Failed: {res.text}")
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
            st.dataframe(df, use_container_width=True, hide_index=True)
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

run_btn = st.button("▶ Run Generation", type="primary", use_container_width=True)

if run_btn:
    try:
        variables = json.loads(variables_input)
    except json.JSONDecodeError:
        st.error("❌ Invalid JSON. Please fix the Variables field.")
        st.stop()

    with st.spinner("Generating and validating output..."):
        try:
            res = requests.post(f"{API_URL}/generate", json={
                "prompt_id": prompt_id,
                "variables": variables,
                "task_type": task_route,
                "stream": enable_stream
            }, timeout=15)
            data = res.json()
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to backend. Make sure `python run_all.py` is running.")
            st.stop()
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            st.stop()

    st.divider()

    if data.get("error"):
        st.error(f"❌ Generation Failed: {data['error']}")
    else:
        st.success("✅ Generation Successful — Schema Valid")

        st.subheader("📤 Output")
        content = data.get("content", {})
        if isinstance(content, dict):
            st.json(content)
        else:
            st.write(content)

        st.subheader("📊 Telemetry")
        usage = data.get("usage", {})
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("⏱ Latency",    f"{data.get('latency_ms', 0)} ms")
        col2.metric("🤖 Model",      data.get("model_used", "—"))
        col3.metric("🔢 Tokens",     usage.get("total_tokens", 0))
        col4.metric("💰 Est. Cost",  f"${usage.get('estimated_cost', 0):.4f}")

# ── A/B COMPARE ────────────────────────────────────────────
st.divider()
with st.expander("⚖️ Compare Two Configurations"):
    st.caption("Run the same input against two different models or prompt versions side by side.")

    try:
        variables = json.loads(variables_input)
    except Exception:
        variables = {}

    col_a, col_b = st.columns(2)
    with col_a:
        prompt_a = st.text_input("Prompt ID A", value="extract_event_v1", key="cmp_a")
        route_a  = st.selectbox("Route A", ["mock", "extraction", "complex_reasoning"], key="route_a")
    with col_b:
        prompt_b = st.text_input("Prompt ID B", value="extract_event_v1", key="cmp_b")
        route_b  = st.selectbox("Route B", ["extraction", "mock", "complex_reasoning"], key="route_b")

    if st.button("⚖️ Run Comparison", use_container_width=True):
        with st.spinner("Running both configurations..."):
            try:
                res_a = requests.post(f"{API_URL}/generate", json={"prompt_id": prompt_a, "variables": variables, "task_type": route_a}, timeout=10).json()
                res_b = requests.post(f"{API_URL}/generate", json={"prompt_id": prompt_b, "variables": variables, "task_type": route_b}, timeout=10).json()

                out_a, out_b = st.columns(2)

                with out_a:
                    if res_a.get("error"):
                        st.error(f"❌ A Failed\n{res_a['error']}")
                    else:
                        st.success("✅ Config A")
                        st.json(res_a.get("content", {}))
                        st.caption(f"⏱ {res_a.get('latency_ms')} ms  |  🤖 {res_a.get('model_used')}  |  🔢 {res_a.get('usage',{}).get('total_tokens',0)} tokens")

                with out_b:
                    if res_b.get("error"):
                        st.error(f"❌ B Failed\n{res_b['error']}")
                    else:
                        st.success("✅ Config B")
                        st.json(res_b.get("content", {}))
                        st.caption(f"⏱ {res_b.get('latency_ms')} ms  |  🤖 {res_b.get('model_used')}  |  🔢 {res_b.get('usage',{}).get('total_tokens',0)} tokens")

            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to backend.")
