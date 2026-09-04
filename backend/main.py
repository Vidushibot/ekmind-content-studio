import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.config import get_settings
from backend.evaluations.dataset_loader import load_golden_dataset, validate_distribution
from backend.schemas.content import ApprovalRequest, ClaimReviewRequest, GenerateRequest, SessionView, SlideGenerationRequest, VideoApprovalRequest, VideoGenerationRequest
from backend.services.content_service import ContentService

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
service = ContentService()


@app.get("/health")
def health() -> dict[str, object]:
    dataset = settings.project_root.parent / "Ekmind_AI_Content_Studio_Golden_Dataset.xlsx"
    dataset_status = "missing"
    if dataset.exists():
        try:
            validate_distribution(load_golden_dataset(dataset))
            dataset_status = "valid"
        except ValueError:
            dataset_status = "invalid"
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "openai",
        "database": settings.database_url.split(":", 1)[0],
        "golden_dataset": dataset_status,
        "capabilities": {
            "research": "configured" if settings.search_api_key else "not_configured",
            "langsmith": "configured" if settings.langsmith_api_key else "not_configured",
            "langsmith_tracing": "enabled" if settings.langsmith_api_key and settings.langsmith_tracing else "disabled",
            "langsmith_project": settings.langsmith_project if settings.langsmith_api_key else None,
            "langsmith_dataset": settings.langsmith_dataset if settings.langsmith_api_key else None,
            "avatar": settings.avatar_provider,
            "voice": settings.voice_provider,
            "youtube": "configured" if settings.youtube_configured else "not_configured",
        },
    }


@app.post("/api/sessions", response_model=SessionView)
def create_session(request: GenerateRequest) -> SessionView:
    return service.create(request)


@app.get("/api/sessions", response_model=list[SessionView])
def list_sessions() -> list[SessionView]:
    return service.list_sessions()


@app.get("/api/sessions/{session_id}", response_model=SessionView)
def get_session(session_id: str) -> SessionView:
    try:
        return service.get(session_id)
    except KeyError as exc:
        raise HTTPException(404, "Session not found") from exc


@app.post("/api/sessions/{session_id}/approve-angle", response_model=SessionView)
def approve_angle(session_id: str, approval: ApprovalRequest) -> SessionView:
    try:
        return service.approve_angle(session_id, approval)
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/approve-content", response_model=SessionView)
def approve_content(session_id: str, approval: ApprovalRequest) -> SessionView:
    try:
        return service.approve_content(session_id, approval)
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/review-claim", response_model=SessionView)
def review_claim(session_id: str, review: ClaimReviewRequest) -> SessionView:
    try:
        return service.review_claim(session_id, review)
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/reevaluate-content", response_model=SessionView)
def reevaluate_content(session_id: str) -> SessionView:
    return run_action(service.reevaluate_content, session_id)


@app.get("/api/library", response_model=list[SessionView])
def library() -> list[SessionView]:
    return service.list_approved()


def run_action(action, session_id: str) -> SessionView:
    try:
        return action(session_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/slides", response_model=SessionView)
def generate_slides(session_id: str, request: SlideGenerationRequest) -> SessionView:
    try:
        return service.generate_slides(session_id, request)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/approve-slides", response_model=SessionView)
def approve_slides(session_id: str) -> SessionView:
    return run_action(service.approve_slides, session_id)


@app.post("/api/sessions/{session_id}/video", response_model=SessionView)
def generate_video(session_id: str, request: VideoGenerationRequest) -> SessionView:
    try:
        return service.generate_video(session_id, request)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/approve-video", response_model=SessionView)
def approve_video(session_id: str, request: VideoApprovalRequest) -> SessionView:
    try:
        return service.approve_video(session_id, request)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/reject-angles", response_model=SessionView)
def reject_angles(session_id: str, approval: ApprovalRequest) -> SessionView:
    try: return service.reject_angles(session_id, approval)
    except (KeyError, ValueError) as exc: raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/reject-content", response_model=SessionView)
def reject_content(session_id: str, approval: ApprovalRequest) -> SessionView:
    try: return service.reject_content(session_id, approval)
    except (KeyError, ValueError) as exc: raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/reject-slides", response_model=SessionView)
def reject_slides(session_id: str, approval: ApprovalRequest) -> SessionView:
    try: return service.reject_slides(session_id, approval)
    except (KeyError, ValueError) as exc: raise HTTPException(409, str(exc)) from exc


@app.post("/api/sessions/{session_id}/reject-video", response_model=SessionView)
def reject_video(session_id: str, approval: ApprovalRequest) -> SessionView:
    try: return service.reject_video(session_id, approval)
    except (KeyError, ValueError) as exc: raise HTTPException(409, str(exc)) from exc


@app.get("/api/evaluations/experiments")
def experiments() -> list[dict]:
    folder = settings.project_root / "storage" / "experiments"
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))] if folder.exists() else []


@app.post("/api/sessions/{session_id}/export-langsmith")
def export_langsmith(session_id: str) -> dict[str, object]:
    try:
        return service.export_to_langsmith(session_id)
    except KeyError as exc:
        raise HTTPException(404, "Session not found") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc
