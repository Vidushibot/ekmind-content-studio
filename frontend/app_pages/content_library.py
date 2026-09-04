import streamlit as st
from client import get
from ui import page_header

page_header("Content library", "Review human-approved content and reuse the strongest ideas across future campaigns.")
try:
    rows = get("/api/library")
    if not rows:
        st.info("No approved content yet.")
    for row in rows:
        request = row["request"]
        with st.expander(request["topic"]):
            with st.container(horizontal=True):
                st.badge(request["audience"], color="blue")
                st.badge(request["tone"], color="orange")
                st.badge(row["status"].replace("_", " ").title(), color="green")
            st.write(row["approved_content"])
            st.caption(f"Revisions: {row['revision_count']} · Similarity: {row['similarity_score']:.1%} · Session: {row['session_id'][:8]}")
except Exception as exc:
    st.error(f"Backend unavailable: {exc}")
