from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class ContentSession(Base):
    __tablename__ = "content_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    workspace_id: Mapped[str] = mapped_column(String(100), index=True)
    topic: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    approved_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkspaceRecord(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="Local workspace")


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(100), index=True)


def scoped_record(name: str, table: str):
    return type(name, (Base,), {"__tablename__": table, "id": mapped_column(String(36), primary_key=True), "workspace_id": mapped_column(String(100), index=True), "session_id": mapped_column(String(36), nullable=True, index=True), "payload": mapped_column(JSON, default=dict)})


AngleRecord = scoped_record("AngleRecord", "angles")
PostRecord = scoped_record("PostRecord", "posts")
HumanFeedbackRecord = scoped_record("HumanFeedbackRecord", "human_feedback")
VoiceProfileRecord = scoped_record("VoiceProfileRecord", "voice_profiles")
ResearchSourceRecord = scoped_record("ResearchSourceRecord", "research_sources")
VerifiedClaimRecord = scoped_record("VerifiedClaimRecord", "verified_claims")
TemplateRecord = scoped_record("TemplateRecord", "templates")
PresentationRecord = scoped_record("PresentationRecord", "presentations")
VideoRecord = scoped_record("VideoRecord", "videos")
EvaluationRunRecord = scoped_record("EvaluationRunRecord", "evaluation_runs")
ExperimentRunRecord = scoped_record("ExperimentRunRecord", "experiment_runs")
