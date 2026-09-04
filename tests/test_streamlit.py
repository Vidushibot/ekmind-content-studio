from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_entrypoint_renders():
    app = Path(__file__).resolve().parents[1] / "frontend" / "streamlit_app.py"
    result = AppTest.from_file(app, default_timeout=10).run()
    assert not result.exception
    assert result.title[0].value == "Content studio"
    assert len(result.tabs) == 5
