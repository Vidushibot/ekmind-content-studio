from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from sqlalchemy import select

from backend.agents import live
from backend.config import get_settings
from backend.database.models import ContentSession
from backend.database.session import Base, SessionLocal, engine
from backend.graph.graph import post_graph, strategy_graph
from backend.schemas.content import ApprovalRequest, ClaimReviewRequest, GenerateRequest, SessionView, SlideGenerationRequest, VideoApprovalRequest, VideoGenerationRequest
from backend.providers.avatar import HeyGenAvatarProvider
from backend.providers.youtube import YouTubeProvider
from backend.services.evaluation_service import content_quality_passes, session_metrics, similarity, unsupported_claims
from backend.evaluations.metrics import assess_faithfulness, extract_factual_claims, faithfulness_score, is_material_claim
from backend.services.langsmith_service import LangSmithService
from backend.services.presentation_service import build_outline, render_deck
from backend.services.video_service import build_video_plan, render_heygen_composite, render_mock_video


class ContentService:
    def __init__(self) -> None:
        Base.metadata.create_all(engine)
        self.settings = get_settings()
        self.langsmith = LangSmithService(self.settings)

    def _save(self, view: SessionView) -> None:
        view.evaluation_metrics = session_metrics(view)
        with SessionLocal.begin() as db:
            row = db.get(ContentSession, view.session_id) or ContentSession(id=view.session_id, user_id=view.user_id, workspace_id=view.workspace_id, topic=view.request.topic, status=view.status, payload={})
            row.status = view.status
            row.payload = view.model_dump(mode="json")
            row.approved_content = view.approved_content
            row.content_approved = view.content_approved
            row.revision_count = view.revision_count
            row.updated_at = datetime.now(timezone.utc)
            db.add(row)

    @staticmethod
    def _record_decision(view: SessionView, stage: str, decision: str, reason: str | None) -> None:
        view.decision_history.append({"stage": stage, "decision": decision, "reason": reason or "", "at": datetime.now(timezone.utc).isoformat()})

    @staticmethod
    def _record_runtime(view: SessionView, stage: str, started: float, provider: str) -> None:
        view.runtime_metrics.append({
            "stage": stage,
            "duration_seconds": round(time.perf_counter() - started, 4),
            "provider": provider,
            "token_consumption": "LANGSMITH_TRACE" if provider != "deterministic" else 0,
            "estimated_api_cost": "LANGSMITH_TRACE" if provider != "deterministic" else 0.0,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _evaluate_retrieval(view: SessionView) -> None:
        if not view.planner.requires_research:
            view.retrieval_evaluation = {
                "mode": "not_required",
                "retrieval_relevance": "NOT_REQUIRED",
            }
            return
        scores = [float(source.relevance_score) for source in view.research_sources if source.relevance_score is not None]
        view.retrieval_evaluation = {
            "mode": "open_web",
            "retrieval_relevance": round(sum(scores) / len(scores), 3) if scores else "NOT_EVALUATED",
            "label_method": "Tavily relevance score plus deterministic query-term overlap",
            "calibration_status": "HEURISTIC_NOT_HUMAN_CALIBRATED",
        }

    @staticmethod
    def _evaluate_faithfulness(view: SessionView, content: str) -> list[str]:
        if not view.planner.requires_research:
            view.claim_assessments = []
            view.faithfulness_score = None
            return []
        claims = extract_factual_claims(content)
        prior_reviews = {str(item.get("claim")): item for item in view.claim_assessments if item.get("human_classification")}
        evidence = [{"evidence_id": source.evidence_id, "text": source.claim, "source_title": source.source_title, "source_url": source.source_url} for source in view.research_sources]
        assessments = assess_faithfulness(claims, evidence)
        rows = []
        for item in assessments:
            prior = prior_reviews.get(item.claim, {})
            human_classification = prior.get("human_classification")
            rows.append({
                "claim": item.claim,
                "sentence_type": item.sentence_type,
                "classification": item.classification,
                "effective_classification": human_classification or item.classification,
                "material": item.material,
                "confidence": item.confidence,
                "match_score": item.score,
                "evidence_ids": list(item.evidence_ids),
                "best_passage": item.best_passage,
                "source_title": item.source_title,
                "source_url": item.source_url,
                "reason": item.reason,
                "signals": list(item.signals),
                "human_classification": human_classification,
                "human_reason": prior.get("human_reason"),
                "reviewed_at": prior.get("reviewed_at"),
                "evaluator_version": "faithfulness-v2",
            })
        view.claim_assessments = rows
        view.faithfulness_score = faithfulness_score(rows)
        return [str(item["claim"]) for item in rows if item["material"] and item["effective_classification"] in {"UNSUPPORTED", "CONTRADICTED"}]

    def review_claim(self, session_id: str, review: ClaimReviewRequest) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_CONTENT_APPROVAL":
            raise ValueError("Claim review is only available before content approval")
        assessment = next((item for item in view.claim_assessments if item.get("claim") == review.claim), None)
        if assessment is None:
            raise ValueError("Claim assessment not found")
        assessment["human_classification"] = review.classification
        assessment["human_reason"] = review.reason
        assessment["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        assessment["effective_classification"] = review.classification
        view.faithfulness_score = faithfulness_score(view.claim_assessments)
        self._record_decision(view, "claim", "HUMAN_REVIEWED", review.reason)
        self._save(view)
        return view

    def create(self, request: GenerateRequest) -> SessionView:
        started = time.perf_counter()
        result = strategy_graph.invoke(
            {"request": request},
            config={"run_name": "content-strategy", "tags": ["content-studio"], "metadata": {"workspace_id": request.workspace_id, "research_mode": str(request.research_mode)}},
        )
        planner = result["planner"]
        sources = result.get("research_sources", [])
        view = SessionView(session_id=str(uuid4()), user_id=request.user_id, workspace_id=request.workspace_id, status="AWAITING_ANGLE_APPROVAL", request=request, planner=planner, candidate_angles=result["candidate_angles"], research_sources=sources, verified_claims=[source.claim for source in sources], evaluation_groups={"Retrieval": "PASS" if sources else ("PENDING" if planner.requires_research else "NOT_REQUIRED"), "Factual & Grounding": "PENDING", "Content Quality": "PENDING", "Human Quality": "AWAITING_INPUT", "Trajectory": "PASS"})
        self._evaluate_retrieval(view)
        self._record_runtime(view, "content_strategy", started, "openai+tavily" if self.settings.openai_api_key else "deterministic")
        self._save(view)
        return view

    def get(self, session_id: str, workspace_id: str = "local-workspace") -> SessionView:
        with SessionLocal() as db:
            row = db.scalar(select(ContentSession).where(ContentSession.id == session_id, ContentSession.workspace_id == workspace_id))
            if row is None:
                raise KeyError(session_id)
            view = SessionView.model_validate(row.payload)
            view.evaluation_metrics = session_metrics(view)
            content_rows = [item for item in view.evaluation_metrics if item["group"] == "3. Content Quality"]
            if content_rows:
                if all(item["status"] == "PASS" for item in content_rows):
                    view.evaluation_groups["Content Quality"] = "PASS"
                elif any(item["status"] == "REVISE" for item in content_rows):
                    view.evaluation_groups["Content Quality"] = "REVISE"
            return view

    def approve_angle(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.angle_approved and view.selected_angle and view.selected_angle.angle_id == approval.angle_id:
            return view
        if view.status != "AWAITING_ANGLE_APPROVAL":
            raise ValueError("Session is not awaiting angle approval")
        angle = next((item for item in view.candidate_angles if item.angle_id == approval.angle_id), None)
        if angle is None:
            raise ValueError("Unknown angle")
        view.selected_angle, view.angle_approved = angle, True
        self._record_decision(view, "angle", "APPROVED", approval.reason)
        started = time.perf_counter()
        result = post_graph.invoke(
            {"request": view.request, "selected_angle": angle, "research_sources": view.research_sources, "max_revisions": view.max_revisions, "quality_threshold": self.settings.quality_threshold},
            config={"run_name": "content-writing", "tags": ["content-studio", "approved-angle"], "metadata": {"session_id": view.session_id, "workspace_id": view.workspace_id}},
        )
        view.current_draft = result["current_draft"]
        view.draft_versions = result["draft_versions"]
        view.critique = result["critique"]
        view.revision_count = result["revision_count"]
        view.status = "AWAITING_CONTENT_APPROVAL"
        view.evaluation_groups["Content Quality"] = "PASS" if content_quality_passes(view.critique) else "REVISE"
        view.evaluation_groups["Human Quality"] = "AWAITING_INPUT"
        self._evaluate_faithfulness(view, view.current_draft)
        self._record_runtime(view, "content_writing", started, "openai" if self.settings.openai_api_key else "deterministic")
        self._save(view)
        return view

    def reevaluate_content(self, session_id: str) -> SessionView:
        view = self.get(session_id)
        content = view.approved_content or view.current_draft
        if not content:
            raise ValueError("Generate content before running faithfulness evaluation")
        self._evaluate_retrieval(view)
        view.unsupported_claims = self._evaluate_faithfulness(view, content)
        view.evaluation_groups["Factual & Grounding"] = "FAIL" if view.unsupported_claims else "PASS"
        self._save(view)
        return view

    def approve_content(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.content_approved and view.status == "PUBLISH_READY":
            return view
        if view.status != "AWAITING_CONTENT_APPROVAL":
            raise ValueError("Session is not awaiting content approval")
        final = (approval.edited_content or view.current_draft or "").strip()
        if not final:
            raise ValueError("Approved content cannot be empty")
        deterministic_unsupported = unsupported_claims(final, view.verified_claims)
        faithfulness_unsupported = self._evaluate_faithfulness(view, final)
        view.unsupported_claims = list(dict.fromkeys(faithfulness_unsupported if view.planner.requires_research else deterministic_unsupported))
        if view.unsupported_claims and self.settings.openai_api_key and view.research_sources:
            final = live.repair_grounding(final, view.unsupported_claims, view.research_sources, self.settings.openai_api_key, self.settings.openai_model)
            view.current_draft = final
            view.draft_versions.append(final)
            deterministic_unsupported = unsupported_claims(final, view.verified_claims)
            faithfulness_unsupported = self._evaluate_faithfulness(view, final)
            view.unsupported_claims = list(dict.fromkeys(faithfulness_unsupported if view.planner.requires_research else deterministic_unsupported))
        if view.unsupported_claims:
            view.evaluation_groups["Factual & Grounding"] = "FAIL"
            self._save(view)
            raise ValueError("Content contains unsupported material factual claims")
        view.approved_content, view.content_approved = final, True
        self._record_decision(view, "content", "APPROVED", approval.reason)
        view.status = "PUBLISH_READY"
        prior = [item.approved_content or "" for item in self.list_approved(view.workspace_id)]
        view.similarity_score = similarity(final, prior)
        view.evaluation_groups["Factual & Grounding"] = "PASS"
        view.evaluation_groups["Human Quality"] = "PASS"
        view.evaluation_groups["Trajectory"] = "PASS"
        view.updated_at = datetime.now(timezone.utc)
        self._save(view)
        return view

    def list_approved(self, workspace_id: str = "local-workspace") -> list[SessionView]:
        with SessionLocal() as db:
            rows = db.scalars(select(ContentSession).where(ContentSession.workspace_id == workspace_id, ContentSession.content_approved.is_(True)).order_by(ContentSession.created_at.desc())).all()
            return [SessionView.model_validate(row.payload) for row in rows]

    def list_sessions(self, workspace_id: str = "local-workspace", limit: int = 50) -> list[SessionView]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(ContentSession)
                .where(ContentSession.workspace_id == workspace_id)
                .order_by(ContentSession.updated_at.desc())
                .limit(limit)
            ).all()
            return [SessionView.model_validate(row.payload) for row in rows]

    def export_to_langsmith(self, session_id: str) -> dict[str, object]:
        view = self.get(session_id)
        result = self.langsmith.export_approved_session(view)
        view.langsmith_export = result
        self._save(view)
        return result

    def generate_slides(self, session_id: str, request: SlideGenerationRequest | None = None) -> SessionView:
        view = self.get(session_id)
        if not view.content_approved or not view.approved_content:
            raise ValueError("Content approval is required before slide generation")
        request = request or SlideGenerationRequest()
        started = time.perf_counter()
        view.slide_design_instructions = request.design_instructions
        if self.settings.openai_api_key:
            view.slide_outline = live.generate_slide_plan(view.request.topic, view.approved_content, request.design_instructions, self.settings.openai_api_key, self.settings.openai_model)
        else:
            view.slide_outline = build_outline(view.request.topic, view.approved_content, request.design_instructions)
        pptx, previews = render_deck(view.session_id, view.slide_outline, self.settings.project_root)
        view.pptx_path = str(pptx); view.slide_previews = [str(p) for p in previews]; view.status = "AWAITING_SLIDE_APPROVAL"
        self._record_runtime(view, "slide_generation", started, "openai" if self.settings.openai_api_key else "deterministic")
        self._save(view); return view

    def reject_angles(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_ANGLE_APPROVAL": raise ValueError("Session is not awaiting angle review")
        self._record_decision(view, "angle", "REJECTED", approval.reason)
        result = strategy_graph.invoke({"request": view.request}); view.candidate_angles = result["candidate_angles"]
        view.research_sources = result.get("research_sources", []); view.verified_claims = [source.claim for source in view.research_sources]
        self._save(view); return view

    def reject_content(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_CONTENT_APPROVAL": raise ValueError("Session is not awaiting content review")
        self._record_decision(view, "content", "REJECTED", approval.reason)
        view.selected_angle = None; view.angle_approved = False; view.current_draft = None; view.critique = None; view.status = "AWAITING_ANGLE_APPROVAL"
        result = strategy_graph.invoke({"request": view.request}); view.candidate_angles = result["candidate_angles"]
        view.research_sources = result.get("research_sources", []); view.verified_claims = [source.claim for source in view.research_sources]
        self._save(view); return view

    def approve_slides(self, session_id: str) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_SLIDE_APPROVAL" or not view.pptx_path:
            raise ValueError("Rendered slides are required before approval")
        view.slides_approved = True; view.status = "SLIDES_APPROVED"; self._record_decision(view, "slides", "APPROVED", None); self._save(view); return view

    def reject_slides(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_SLIDE_APPROVAL": raise ValueError("Session is not awaiting slide review")
        self._record_decision(view, "slides", "REJECTED", approval.reason)
        view.slide_outline = []; view.slide_previews = []; view.pptx_path = None; view.slides_approved = False; view.status = "PUBLISH_READY"
        self._save(view); return view

    def generate_video(self, session_id: str, request: VideoGenerationRequest | None = None) -> SessionView:
        view = self.get(session_id)
        if not view.slides_approved:
            raise ValueError("Slide approval is required before video generation")
        view.video_script, view.scene_plan = build_video_plan(view.slide_outline)
        started = time.perf_counter()
        request = request or VideoGenerationRequest()
        if self.settings.avatar_provider.lower() == "heygen":
            if not request.confirm_paid_render:
                raise ValueError("Confirm the paid HeyGen render before generating this video")
            source = self.settings.project_root / "storage" / view.session_id / "video" / "heygen-avatar.mp4"
            can_reuse = view.status == "AWAITING_VIDEO_APPROVAL" and source.is_file() and bool(view.video_validation.get("source_duration_seconds"))
            if can_reuse:
                source_duration = float(view.video_validation["source_duration_seconds"])
                job_id = str(view.video_validation.get("provider_job_id", "reused"))
            else:
                provider = HeyGenAvatarProvider(self.settings.heygen_api_key or "", self.settings.heygen_avatar_id or "", self.settings.heygen_voice_id or "", self.settings.heygen_api_base)
                idempotency_key = f"ekmind-{view.session_id}-{int(view.updated_at.timestamp())}"
                job_id = provider.create_video(view.video_script, f"Ekmind — {view.request.topic}", idempotency_key)
                result = provider.wait_for_video(job_id)
                source = provider.download(str(result["video_url"]), source)
                source_duration = float(result.get("duration") or 60)
            video, srt, validation = render_heygen_composite(view.session_id, view.scene_plan, view.slide_previews, source, source_duration, self.settings.project_root)
            validation.update({"provider_job_id": job_id, "source_duration_seconds": source_duration, "source_reused": can_reuse})
        else:
            video, srt, validation = render_mock_video(view.session_id, view.scene_plan, view.slide_previews, self.settings.project_root)
        view.video_path = str(video); view.subtitle_path = str(srt); view.video_validation = validation; view.status = "AWAITING_VIDEO_APPROVAL"
        self._record_runtime(view, "video_generation", started, self.settings.avatar_provider.lower())
        self._save(view); return view

    def approve_video(self, session_id: str, request: VideoApprovalRequest | None = None) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_VIDEO_APPROVAL" or view.video_validation.get("status") != "PASS":
            raise ValueError("A validated video is required before approval")
        request = request or VideoApprovalRequest()
        if request.publish_to_youtube and view.youtube_publish.get("status") != "uploaded":
            if not self.settings.youtube_configured:
                raise ValueError("YouTube OAuth is not configured. Add YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN to .env")
            title = (request.youtube_title or f"Ekmind — {view.request.topic}").strip()
            description = (request.youtube_description or view.approved_content or "").strip()
            if not title:
                raise ValueError("A YouTube title is required")
            provider = YouTubeProvider(
                self.settings.youtube_client_id or "",
                self.settings.youtube_client_secret or "",
                self.settings.youtube_refresh_token or "",
            )
            view.youtube_publish = provider.upload_private(Path(view.video_path or ""), title, description)
            view.youtube_publish.update({"title": title[:100], "uploaded_at": datetime.now(timezone.utc).isoformat()})
            self._save(view)
        view.video_approved = True; view.status = "DONE"; self._record_decision(view, "video", "APPROVED", None); self._save(view); return view

    def reject_video(self, session_id: str, approval: ApprovalRequest) -> SessionView:
        view = self.get(session_id)
        if view.status != "AWAITING_VIDEO_APPROVAL": raise ValueError("Session is not awaiting video review")
        self._record_decision(view, "video", "REJECTED", approval.reason)
        view.video_script = None; view.scene_plan = []; view.video_path = None; view.subtitle_path = None; view.video_validation = {}; view.video_approved = False; view.status = "SLIDES_APPROVED"
        self._save(view); return view
