import streamlit as st
from client import get
from ui import page_header

page_header("System settings", "A live view of connected models, research, observability, media providers, and presentation styling.")
try:
    health = get("/health")
    capabilities = health["capabilities"]
    model, governance, media = st.columns(3)
    with model.container(border=True):
        st.subheader("Intelligence")
        st.metric("OpenAI", "Connected" if health["mode"] == "openai" else "Demo mode")
        st.write("Research", capabilities["research"].replace("_", " ").title())
        st.write("Database", health["database"].upper())
    with governance.container(border=True):
        st.subheader("Governance")
        st.metric("LangSmith", "Connected" if capabilities["langsmith"] == "configured" else "Not connected")
        st.write("Tracing", capabilities["langsmith_tracing"].title())
        st.write("Golden dataset", health["golden_dataset"].title())
    with media.container(border=True):
        st.subheader("Production")
        st.metric("Avatar", capabilities["avatar"].title())
        st.write("Voice", capabilities["voice"].title())
        st.write("YouTube private upload", "Connected" if capabilities.get("youtube") == "configured" else "Not connected")
        st.write("Deck style", "HR Mythbuster")
    if capabilities["langsmith"] == "configured":
        with st.expander("LangSmith details"):
            st.write("Project", capabilities["langsmith_project"])
            st.write("Dataset", capabilities["langsmith_dataset"])
except Exception as exc:
    st.error(f"Backend unavailable: {exc}")
