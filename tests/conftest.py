import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
TEST_DATABASE_DIR = Path(tempfile.mkdtemp(prefix="ekmind-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DATABASE_DIR / 'test.db').as_posix()}"
os.environ["AVATAR_PROVIDER"] = "mock"
os.environ["VOICE_PROVIDER"] = "mock"
os.environ["OPENAI_API_KEY"] = ""
os.environ["SEARCH_API_KEY"] = ""
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["YOUTUBE_CLIENT_ID"] = ""
os.environ["YOUTUBE_CLIENT_SECRET"] = ""
os.environ["YOUTUBE_REFRESH_TOKEN"] = ""
