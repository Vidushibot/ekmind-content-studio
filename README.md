# Ekmind AI Content Studio

Local MVP implementation of a governed, human-in-the-loop content workflow spanning strategy, post, evaluation, slides, and video.

## Implemented

- FastAPI health, session, approval, and approved-library endpoints
- Streamlit navigation: Content Studio, Content Library, Evaluations, Settings
- Strategy/Post vertical slice: planner → three distinct angles → mandatory angle approval → writer → independent critic → bounded revision loop → mandatory content approval
- SQLite development persistence with workspace-scoped reads; `DATABASE_URL` can later point to PostgreSQL
- Five-group evaluation summary shell
- Read-only loading and distribution validation of the provided 40-case Golden Dataset
- Factual-claim extraction, unsupported-claim hard gate, deterministic similarity, and human-edit utilities
- Workspace-scoped models for the required business record types; PostgreSQL/pgvector drivers and Alembic are ready for configuration
- Configuration-driven eight-slide outline, editable PPTX generation, reopen validation, preview images, and mandatory slide approval
- `Template.pptx` is copied per session and its master/theme/layouts are used; the source template is never modified
- Explicit reject/regenerate actions for angles, content, slides, and video, with reasons recorded in decision history
- Avatar and voice provider interfaces with clearly labeled mock implementations
- Video script and scene plan, SRT captions, local FFmpeg MP4 composition at 1920×1080/30fps with audio stream, validation, and mandatory video approval
- Optional final YouTube upload through OAuth, always created with `privacyStatus=private`
- Preserved Golden Dataset experiments: `baseline_v1`, `post_improvement_v2`, and `post_improvement_v3`
- Safe startup when OpenAI, LangSmith, search, avatar, and voice providers are unconfigured

The current no-key mode is explicitly deterministic demo mode. It exercises workflow, artifact generation, regression evaluation, and HITL controls but does not pretend to perform live LLM generation, web research, LangSmith tracing, avatar speech, or voice synthesis.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
.venv\Scripts\python -m streamlit run frontend/streamlit_app.py
```

FastAPI: <http://127.0.0.1:8000>  
Streamlit: <http://localhost:8501>

Run tests with `.venv\Scripts\python -m pytest`.

## Zero-cost evaluation

Run the actual LangGraph topology with deterministic provider substitutions. This mode disables LangSmith tracing and makes no OpenAI, Tavily, HeyGen, YouTube, or other paid-provider calls:

```powershell
.venv\Scripts\python -m backend.evaluations.cli --split validation --experiment free_validation_v1
```

The command writes immutable JSON and HTML reports to `storage/experiments` and refreshes `evaluation_data/golden_manifest.json`. Choose a new experiment ID for every candidate, or explicitly use `--overwrite` while developing. A workflow suite may pass while `release_ready` remains false: retrieval and faithfulness cannot pass the release gate until human-adjudicated evidence and claim mappings are added to `evaluation_data/evidence.json` and `evaluation_data/claims.json`.

## Configuration-dependent capabilities

- Live OpenAI generation requires `OPENAI_API_KEY`.
- Live research requires a configured search provider and key.
- LangSmith trace/dataset upload requires `LANGSMITH_API_KEY`.
- PostgreSQL and pgvector require a running PostgreSQL server and a PostgreSQL `DATABASE_URL`.
- Branded rendering now uses the supplied `Template.pptx`; additional logo/brand assets can still be configured later.
- Synthesia/HeyGen/ElevenLabs calls require their provider credentials and remain disabled by default.
- Private YouTube upload requires `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` from an OAuth grant with the `youtube.upload` scope.

The current mock video is a validated technical composition with silence, not a human-avatar performance. Preview PNGs approximate the supplied template for UI review; PowerPoint/Keynote rendering parity has not been checked because no compatible desktop/headless Office renderer is installed.

## Regression experiments

The unchanged 40-case Golden Dataset produced:

- `baseline_v1`: 25/40 routing checks passed
- `post_improvement_v2`: 35/40 passed
- `post_improvement_v3`: 40/40 passed

These are deterministic local routing experiments, not LangSmith or LLM-judge experiments. Historical result files are retained in `storage/experiments`.

No LinkedIn publishing is implemented.
