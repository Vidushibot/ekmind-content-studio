import streamlit as st
from ui import install_brand_details

st.set_page_config(page_title="Ekmind AI Content Studio", page_icon=":material/auto_awesome:", layout="wide", initial_sidebar_state="collapsed")
st.session_state.setdefault("session", None)
install_brand_details()
page = st.navigation([
    st.Page("app_pages/content_studio.py", title="Content Studio", icon=":material/edit_note:", default=True),
    st.Page("app_pages/content_library.py", title="Content Library", icon=":material/library_books:"),
    st.Page("app_pages/evaluations.py", title="Evaluations", icon=":material/analytics:"),
    st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:"),
], position="top")
page.run()
