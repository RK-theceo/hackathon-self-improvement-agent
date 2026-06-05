"""
app.py
------
SelfCode — Self-Improving Code Generation Agent
Streamlit UI with two tabs:
  Tab 1: Run Agent (task input → iterative code generation loop)
  Tab 2: Memory Log (view and clear memory.json)

Run with: streamlit run app.py
"""

import sys
import os

# Ensure project root is on the path so relative imports work
sys.path.insert(0, os.path.dirname(__file__))

import json
import streamlit as st
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import project modules
from memory import search_memory, write_memory, clear_memory, format_memory_hints
from agents.generator import run_generator
from agents.executor import run_executor
from agents.validator import run_validator

# ─────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SelfCode — Self-Improving Agent",
    page_icon="🤖",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(90deg, #7c3aed, #2563eb);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #6b7280;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }
    .iter-header {
        font-weight: 700;
        font-size: 1.1rem;
    }
    .pass-badge {
        background: #d1fae5;
        color: #065f46;
        padding: 2px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .fail-badge {
        background: #fee2e2;
        color: #991b1b;
        padding: 2px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .memory-banner {
        background: #ede9fe;
        border-left: 4px solid #7c3aed;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .overconfidence-banner {
        background: #fef9c3;
        border-left: 4px solid #eab308;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">🤖 SelfCode</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Self-Improving Code Generation Agent · AutoGen + Groq (Llama 3)</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🚀 Run Agent", "🧠 Memory Log"])


# ═══════════════════════════════════════════════════════════════
# TAB 1 — Run Agent
# ═══════════════════════════════════════════════════════════════
with tab1:

    col1, col2 = st.columns([2, 1])

    with col1:
        task_input = st.text_area(
            "📝 Task Description",
            height=150,
            placeholder=(
                "Describe what you want the code to do.\n"
                "Examples:\n"
                "  • Write a Python function to find the longest palindrome substring\n"
                "  • Create an HTML page with a dark-mode toggle\n"
                "  • Write a bash script that backs up /home to a timestamped zip\n"
                "  • Scrape the top 5 headlines from news.ycombinator.com"
            ),
        )

    with col2:
        expected_output = st.text_input(
            "✅ Expected Output (optional)",
            placeholder="e.g. 'racecar' or '120'",
            help="If provided, the validator compares exact output. Leave blank for exit-code-only validation.",
        )
        st.markdown("&nbsp;", unsafe_allow_html=True)
        run_button = st.button("▶️ Run SelfCode", use_container_width=True, type="primary")

    # ── Run the agent loop ──────────────────────────────────────
    if run_button:

        if not task_input.strip():
            st.error("Please enter a task description.")
            st.stop()

        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            st.error(
                "❌ GROQ_API_KEY not set. Add it to your `.env` file:\n```\nGROQ_API_KEY=your_key_here\n```"
            )
            st.stop()

        st.divider()

        # ── Memory search ───────────────────────────────────────
        memory_matches = search_memory(task_input)
        memory_hints = format_memory_hints(memory_matches)
        memory_used = bool(memory_matches)

        if memory_used:
            st.markdown(
                f"""<div class="memory-banner">
                🧠 <strong>Memory active:</strong> Found {len(memory_matches)} similar past task(s).
                Injecting error-avoidance hints into the generator prompt.
                </div>""",
                unsafe_allow_html=True,
            )
            with st.expander("🔍 View matched memory entries"):
                for i, entry in enumerate(memory_matches, 1):
                    st.json(entry)

        # ── Agent loop state ────────────────────────────────────
        MAX_ITERATIONS = 3
        iterations_data = []       # list of dicts, one per iteration
        final_passed = False
        final_code = ""
        final_language = "python"
        any_overconfident = False
        last_error_category = "none"

        previous_code = None
        error_output = None
        error_category = None

        # ── Iterate ─────────────────────────────────────────────
        for iteration in range(1, MAX_ITERATIONS + 1):

            iter_label = f"Iteration {iteration} / {MAX_ITERATIONS}"
            with st.expander(f"🔄 {iter_label}", expanded=True):

                st.markdown(f"**{iter_label} — Generating code...**")

                # ── STEP 1: Generate ────────────────────────────
                with st.spinner("🧠 GeneratorAgent thinking..."):
                    gen_result = run_generator(
                        task=task_input,
                        iteration=iteration,
                        previous_code=previous_code,
                        error_output=error_output,
                        error_category=error_category,
                        memory_hints=memory_hints if memory_used else None,
                        expected_output=expected_output if expected_output.strip() else None,
                    )

                language = gen_result["language"]
                dependencies = gen_result["dependencies"]
                code = gen_result["code"]
                confidence_score = gen_result["confidence_score"]
                confidence_reason = gen_result["confidence_reason"]

                # Display generation details
                col_lang, col_conf = st.columns([1, 1])
                with col_lang:
                    st.markdown(f"**Language detected:** `{language.upper()}`")
                    if dependencies:
                        st.markdown(
                            f"**Dependencies to install:** `{', '.join(dependencies)}`"
                        )
                    else:
                        st.markdown("**Dependencies:** none")

                with col_conf:
                    st.markdown(f"**Confidence: {confidence_score}/10**")
                    st.progress(confidence_score / 10, text=f"{confidence_reason}")

                st.markdown("**Generated Code:**")
                st.code(code, language=language)

                # ── STEP 2: Execute ─────────────────────────────
                with st.spinner("⚙️ ExecutorAgent running code..."):
                    exec_result = run_executor(
                        language=language,
                        code=code,
                        dependencies=dependencies,
                    )

                if exec_result["install_log"]:
                    with st.expander("📦 Dependency install log"):
                        st.text(exec_result["install_log"])

                if exec_result["success"]:
                    st.success("✅ Execution succeeded")
                else:
                    st.error("❌ Execution failed")

                if exec_result["output"]:
                    st.markdown("**Execution Output (stdout):**")
                    st.text(exec_result["output"])

                if exec_result["error"]:
                    st.markdown("**Execution Error (stderr):**")
                    st.code(exec_result["error"], language="bash")

                # ── STEP 3: Validate ────────────────────────────
                with st.spinner("🔍 ValidatorAgent checking results..."):
                    val_result = run_validator(
                        language=language,
                        exec_success=exec_result["success"],
                        actual_output=exec_result["output"],
                        error_text=exec_result["error"],
                        error_type_hint=exec_result["error_type"],
                        confidence_score=confidence_score,
                        expected_output=expected_output if expected_output.strip() else None,
                        iteration=iteration,
                    )

                passed = val_result["passed"]
                val_error_category = val_result["error_category"]
                overconfident = val_result["overconfident"]
                feedback = val_result["feedback"]

                if overconfident:
                    any_overconfident = True

                # Validator result display
                if passed:
                    st.markdown(
                        '<span class="pass-badge">✅ VALIDATION PASSED</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<span class="fail-badge">❌ VALIDATION FAILED</span> &nbsp; '
                        f'Error category: <code>{val_error_category}</code>',
                        unsafe_allow_html=True,
                    )
                    if overconfident:
                        st.warning(
                            "⚠️ Overconfidence detected: generator rated confidence "
                            f"{confidence_score}/10 but validation failed."
                        )
                    if iteration < MAX_ITERATIONS:
                        st.info(f"💬 Feedback for next iteration:\n\n{feedback}")

                # Store iteration data for summary
                iterations_data.append(
                    {
                        "iteration": iteration,
                        "language": language,
                        "dependencies": dependencies,
                        "code": code,
                        "confidence_score": confidence_score,
                        "confidence_reason": confidence_reason,
                        "exec_success": exec_result["success"],
                        "exec_output": exec_result["output"],
                        "exec_error": exec_result["error"],
                        "passed": passed,
                        "error_category": val_error_category,
                        "overconfident": overconfident,
                        "feedback": feedback,
                    }
                )

                # Prepare for next iteration if needed
                final_passed = passed
                final_code = code
                final_language = language
                last_error_category = val_error_category or "none"

                if passed:
                    break  # Success — stop loop
                else:
                    # Carry context into next iteration
                    previous_code = code
                    error_output = (exec_result["error"] or "") + "\n" + feedback
                    error_category = val_error_category

        # ── Post-loop summary ───────────────────────────────────
        st.divider()
        st.markdown("## 📊 Run Summary")

        # Final status
        if final_passed:
            st.success("🎉 Task completed successfully!")
        else:
            st.error("💔 All 3 iterations failed. Final code shown below.")

        # Confidence journey
        st.markdown("### 📈 Confidence Journey")
        journey_parts = []
        for d in iterations_data:
            icon = "✅" if d["passed"] else "❌"
            journey_parts.append(
                f"Iteration {d['iteration']}: **{d['confidence_score']}/10** {icon}"
            )
        st.markdown("  →  ".join(journey_parts))

        # Overconfidence banner
        if any_overconfident:
            st.markdown(
                """<div class="overconfidence-banner">
                ⚠️ <strong>Overconfidence detected</strong> during this run.
                The model rated its confidence ≥ 7 on at least one iteration that subsequently failed.
                This has been recorded in memory to help future runs.
                </div>""",
                unsafe_allow_html=True,
            )

        # Memory used banner
        if memory_used:
            st.markdown(
                f"""<div class="memory-banner">
                🧠 <strong>Memory was used</strong> in this run ({len(memory_matches)} match(es) found).
                Past error hints were injected into the generator prompt.
                </div>""",
                unsafe_allow_html=True,
            )

        # Final code
        st.markdown("### 💻 Final Code")
        st.code(final_code, language=final_language)

        # ── Write to memory ──────────────────────────────────────
        # Determine best fix summary
        if final_passed and len(iterations_data) > 1:
            fix_summary = (
                f"Fixed {iterations_data[-2]['error_category']} after "
                f"{len(iterations_data)} iterations"
            )
        elif final_passed:
            fix_summary = "Passed on first attempt"
        else:
            fix_summary = f"All iterations failed; last error: {last_error_category}"

        # Final confidence = last iteration's score
        final_conf = iterations_data[-1]["confidence_score"] if iterations_data else 5

        write_memory(
            task=task_input,
            task_type=final_language,
            error_type=last_error_category,
            fix_summary=fix_summary,
            iterations_needed=len(iterations_data),
            final_confidence=final_conf,
            overconfident_flagged=any_overconfident,
        )

        st.caption("✍️ Run recorded to memory.json")


# ═══════════════════════════════════════════════════════════════
# TAB 2 — Memory Log
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 🧠 Memory Log")
    st.markdown(
        "All past runs are stored here. The agent uses this to avoid repeating past mistakes."
    )

    # Load and display memory
    memory_file_path = os.path.join(os.path.dirname(__file__), "memory.json")

    try:
        with open(memory_file_path, "r", encoding="utf-8") as f:
            raw_memory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raw_memory = []

    if not raw_memory:
        st.info("No memory entries yet. Run a task to populate memory.")
    else:
        st.success(f"📚 {len(raw_memory)} memory entries stored.")

        # Build a display-friendly list (flatten task_keywords for the table)
        display_rows = []
        for entry in raw_memory:
            display_rows.append(
                {
                    "timestamp": entry.get("timestamp", ""),
                    "task_type": entry.get("task_type", ""),
                    "error_type": entry.get("error_type", ""),
                    "fix_summary": entry.get("fix_summary", ""),
                    "iterations": entry.get("iterations_needed", ""),
                    "final_confidence": entry.get("final_confidence", ""),
                    "overconfident": entry.get("overconfident_flagged", False),
                    "keywords": ", ".join(entry.get("task_keywords", [])),
                }
            )

        import pandas as pd
        df = pd.DataFrame(display_rows)
        st.dataframe(df, use_container_width=True)

        # Show raw JSON in expander
        with st.expander("🔎 View raw memory.json"):
            st.json(raw_memory)

    st.divider()

    # Clear memory button
    if st.button("🗑️ Clear Memory", type="secondary"):
        clear_memory()
        st.success("Memory cleared. memory.json reset to empty list [].")
        st.rerun()
