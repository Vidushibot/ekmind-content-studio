import streamlit as st
from client import ApiError, get, post
from ui import page_header

page_header("Evaluation centre", "See quality gates, human-review signals, trajectory health, and LangSmith exports in one place.")
session = st.session_state.get("session")
try:
    saved_sessions = get("/api/sessions")
except ApiError:
    saved_sessions = []
if saved_sessions:
    session_ids = [item["session_id"] for item in saved_sessions]
    current_id = session.get("session_id") if session else session_ids[0]
    selected_id = st.selectbox(
        "Evaluation session",
        session_ids,
        index=session_ids.index(current_id) if current_id in session_ids else 0,
        format_func=lambda session_id: next(
            f"{item['request']['topic'][:70]} — {item['status'].replace('_', ' ').title()}"
            for item in saved_sessions
            if item["session_id"] == session_id
        ),
        key="evaluation_session_id",
    )
    session = next(item for item in saved_sessions if item["session_id"] == selected_id)
    st.session_state.session = session
elif session:
    try:
        session = get(f"/api/sessions/{session['session_id']}")
        st.session_state.session = session
    except ApiError:
        pass

st.write("Five governed evaluation groups cover retrieval, grounding, content, human review, and workflow trajectory.")
if session:
    metrics = session.get("evaluation_metrics", [])
    summary = session.get("evaluation_groups", {})
    summary_columns = st.columns(5)
    for column, label in zip(summary_columns, ["Retrieval", "Factual & Grounding", "Content Quality", "Human Quality", "Trajectory"]):
        column.metric(label, summary.get(label, "Pending"))
    for group in ["1. Retrieval Quality", "2. Factual & Grounding", "3. Content Quality", "4. Human Quality", "5. Trajectory"]:
        rows = [
            {
                "Metric": row["metric"],
                "Value": row["value"],
                "Status": row["status"],
                "Target": row["target"],
                "Evaluation approach": row["approach"],
            }
            for row in metrics
            if row["group"] == group
        ]
        with st.expander(group, expanded=group in {"2. Factual & Grounding", "3. Content Quality"}):
            st.dataframe(
                rows,
                hide_index=True,
                column_config={
                    "Metric": st.column_config.TextColumn(pinned=True),
                    "Value": st.column_config.TextColumn(),
                    "Status": st.column_config.TextColumn(),
                    "Target": st.column_config.TextColumn(),
                    "Evaluation approach": st.column_config.TextColumn(width="large"),
                },
            )
    if session.get("current_draft") and session.get("planner", {}).get("requires_research"):
        if st.button("Re-evaluate claim evidence", icon=":material/refresh:"):
            try:
                st.session_state.session = post(f"/api/sessions/{session['session_id']}/reevaluate-content", {})
                st.rerun()
            except ApiError as exc:
                st.error(f"Could not re-evaluate content: {exc}")
    claim_assessments = session.get("claim_assessments", [])
    if claim_assessments:
        st.subheader("Claim evidence review")
        st.caption("Automated classifications use focused evidence passages. Human decisions are persisted and become the effective classification.")
        counts = {}
        for assessment in claim_assessments:
            effective = assessment.get("effective_classification") or assessment.get("classification", "UNKNOWN")
            counts[effective] = counts.get(effective, 0) + 1
        with st.container(horizontal=True):
            for label in ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NEEDS_HUMAN_REVIEW"]:
                st.metric(label.replace("_", " ").title(), counts.get(label, 0))
        for index, assessment in enumerate(claim_assessments):
            effective = assessment.get("effective_classification") or assessment.get("classification")
            reviewed = bool(assessment.get("human_classification"))
            heading = f"{effective.replace('_', ' ').title()} — {'Material' if assessment.get('material') else 'Non-material'}"
            with st.expander(heading, expanded=effective in {"UNSUPPORTED", "CONTRADICTED", "NEEDS_HUMAN_REVIEW"}):
                st.write("**Claim:**", assessment.get("claim"))
                st.write("**Reason:**", assessment.get("reason"))
                st.write("**Best evidence passage:**", assessment.get("best_passage") or "No passage matched")
                st.caption(f"Match {float(assessment.get('match_score', 0)):.3f} · Confidence {float(assessment.get('confidence', 0)):.3f} · Evaluator {assessment.get('evaluator_version', 'unknown')}")
                if assessment.get("signals"):
                    st.write("Signals:", ", ".join(assessment["signals"]))
                if assessment.get("source_url"):
                    st.link_button("Open evidence source", assessment["source_url"], icon=":material/open_in_new:")
                if reviewed:
                    st.success(f"Human reviewed as {assessment['human_classification'].replace('_', ' ').title()}: {assessment.get('human_reason', '')}")
                if session.get("status") == "AWAITING_CONTENT_APPROVAL":
                    classification = st.selectbox(
                        "Human classification",
                        ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE"],
                        index=0 if effective not in {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE"} else ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE"].index(effective),
                        key=f"claim_classification_{index}",
                    )
                    reason = st.text_input("Review reason", key=f"claim_reason_{index}", placeholder="Explain why the evidence supports or does not support this claim")
                    if st.button("Save human review", key=f"save_claim_review_{index}", icon=":material/fact_check:", disabled=len(reason.strip()) < 3):
                        try:
                            st.session_state.session = post(
                                f"/api/sessions/{session['session_id']}/review-claim",
                                {"claim": assessment["claim"], "classification": classification, "reason": reason},
                            )
                            st.rerun()
                        except ApiError as exc:
                            st.error(f"Could not save claim review: {exc}")
    st.caption("Not evaluated means the metric requires labeled evidence or a dedicated judge run that is not available for this session; no score is inferred.")
else:
    st.info("Create a content session to populate the evaluation metrics.")
try:
    health = get("/health")
    capabilities = health["capabilities"]
    tracing_enabled = capabilities["langsmith_tracing"] == "enabled"
    with st.container(border=True):
        st.subheader("LangSmith")
        st.write("Tracing:", "Enabled" if tracing_enabled else "Disabled")
        if capabilities["langsmith"] == "configured":
            st.write("Project:", capabilities["langsmith_project"])
            st.write("Approved-content dataset:", capabilities["langsmith_dataset"])
            if session and session.get("content_approved"):
                if st.button("Export approved example", icon=":material/cloud_upload:", type="primary"):
                    try:
                        result = post(f"/api/sessions/{session['session_id']}/export-langsmith", {}, timeout=90)
                        session["langsmith_export"] = result
                        st.session_state.session = session
                        st.success(f"Exported to {result['dataset']}.")
                    except ApiError as exc:
                        st.error(f"LangSmith export failed: {exc}")
            else:
                st.info("Approve content to enable dataset export.")
        else:
            st.warning("Add LANGSMITH_API_KEY to enable tracing and export.")
except Exception as exc:
    st.error(f"Could not load LangSmith status: {exc}")
st.subheader("Golden Dataset experiments")
try:
    experiments = get("/api/evaluations/experiments")
    if experiments:
        st.dataframe([{"Experiment": e["experiment_id"], "Cases": e["cases"], "Passed": e["passed"], "Trajectory success": f"{e['trajectory_success']:.1%}", "Latency (s)": e["latency_seconds"]} for e in experiments], hide_index=True)
    else:
        st.info("No local experiments recorded yet.")
except Exception as exc:
    st.error(f"Could not load experiments: {exc}")
