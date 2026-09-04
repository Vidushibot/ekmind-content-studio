from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ResearchMode(StrEnum):
    AUTO = "Auto"
    ALWAYS = "Always"
    SKIP = "Skip"


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    objective: str = "Thought Leadership"
    audience: str = "General Professional Audience"
    tone: str = "Professional"
    research_mode: ResearchMode = ResearchMode.AUTO
    target_length: str = "Medium"
    user_id: str = "local-user"
    workspace_id: str = "local-workspace"


class PlannerResult(BaseModel):
    intent: str
    content_type: str = "LinkedIn thought-leadership post"
    interpreted_topic: str
    audience: str
    tone: str
    requires_research: bool
    reason_research_required: str
    ambiguity_detected: bool = False
    clarification_required: bool = False


class Angle(BaseModel):
    angle_id: str = Field(default_factory=lambda: str(uuid4()))
    angle_type: str
    hook: str
    thesis: str
    key_points: list[str]
    why_it_matters: str
    audience_fit: str
    novelty_score: float = Field(ge=0, le=10)


class CritiqueResult(BaseModel):
    clarity: float = Field(ge=0, le=10)
    value: float = Field(ge=0, le=10)
    engagement: float = Field(ge=0, le=10)
    tone: float = Field(ge=0, le=10)
    originality: float = Field(ge=0, le=10)
    voice_match: float = Field(ge=0, le=10)
    audience_relevance: float = Field(ge=0, le=10)
    strengths: list[str]
    weaknesses: list[str]
    required_changes: list[str]
    generic_language_detected: bool = False

    @property
    def overall(self) -> float:
        scores = [self.clarity, self.value, self.engagement, self.tone, self.originality, self.voice_match, self.audience_relevance]
        return round(sum(scores) / len(scores), 2)


class ApprovalRequest(BaseModel):
    angle_id: str | None = None
    edited_content: str | None = None
    reason: str | None = None


class ClaimReviewRequest(BaseModel):
    claim: str = Field(min_length=3)
    classification: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE"]
    reason: str = Field(min_length=3, max_length=1000)


class VideoGenerationRequest(BaseModel):
    confirm_paid_render: bool = False


class VideoApprovalRequest(BaseModel):
    publish_to_youtube: bool = False
    youtube_title: str | None = Field(default=None, max_length=100)
    youtube_description: str | None = Field(default=None, max_length=5000)


class SlideGenerationRequest(BaseModel):
    design_instructions: str = Field(
        default="Be creative and visual-led. Use varied layouts, relevant visuals, diagrams or charts where they strengthen the message. Keep copy concise and ensure every element fits safely inside the slide frame without clipping or overlap.",
        max_length=1000,
    )


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    claim: str
    source_title: str
    source_url: str
    publisher: str
    confidence: float = Field(ge=0, le=1)
    verification_status: str
    retrieval_rank: int | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    relevance_label: Literal["RELEVANT", "PARTIALLY_RELEVANT", "NOT_RELEVANT", "NOT_EVALUATED"] = "NOT_EVALUATED"


class Slide(BaseModel):
    slide_number: int
    slide_type: str
    title: str
    content: list[str]
    speaker_notes: str = ""
    visual_type: Literal["concept", "process", "timeline", "comparison", "quote", "metric", "closing"] = "concept"
    visual_labels: list[str] = []


class Scene(BaseModel):
    scene_id: str = Field(default_factory=lambda: str(uuid4()))
    scene_type: str
    spoken_text: str
    slide_number: int | None = None
    avatar_enabled: bool = False
    duration_target: float = 8.0


class SessionView(BaseModel):
    session_id: str
    user_id: str
    workspace_id: str
    status: str
    request: GenerateRequest
    planner: PlannerResult
    candidate_angles: list[Angle]
    selected_angle: Angle | None = None
    angle_approved: bool = False
    current_draft: str | None = None
    draft_versions: list[str] = []
    critique: CritiqueResult | None = None
    revision_count: int = 0
    max_revisions: int = 2
    content_approved: bool = False
    approved_content: str | None = None
    research_sources: list[Evidence] = []
    verified_claims: list[str] = []
    unsupported_claims: list[str] = []
    retrieval_evaluation: dict[str, object] = {}
    claim_assessments: list[dict[str, object]] = []
    faithfulness_score: float | None = None
    similarity_score: float = 0.0
    slide_outline: list[Slide] = []
    slide_design_instructions: str | None = None
    slides_approved: bool = False
    pptx_path: str | None = None
    slide_previews: list[str] = []
    video_script: str | None = None
    scene_plan: list[Scene] = []
    video_approved: bool = False
    video_path: str | None = None
    subtitle_path: str | None = None
    video_validation: dict[str, object] = {}
    youtube_publish: dict[str, object] = {}
    decision_history: list[dict[str, object]] = []
    evaluation_groups: dict[str, str]
    evaluation_metrics: list[dict[str, object]] = []
    langsmith_export: dict[str, object] = {}
    runtime_metrics: list[dict[str, object]] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def approval_invariants(self) -> "SessionView":
        if self.angle_approved and self.selected_angle is None:
            raise ValueError("angle approval requires a selected angle")
        if self.content_approved and not self.approved_content:
            raise ValueError("content approval requires approved content")
        return self
