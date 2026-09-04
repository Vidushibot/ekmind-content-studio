from typing import TypedDict

from backend.schemas.content import Angle, CritiqueResult, Evidence, GenerateRequest, PlannerResult


class ContentStudioState(TypedDict, total=False):
    request: GenerateRequest
    planner: PlannerResult
    candidate_angles: list[Angle]
    research_sources: list[Evidence]
    selected_angle: Angle
    current_draft: str
    draft_versions: list[str]
    critique: CritiqueResult
    revision_count: int
    max_revisions: int
    quality_threshold: float
