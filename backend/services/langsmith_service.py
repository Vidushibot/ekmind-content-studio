from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langsmith import Client

from backend.config import Settings
from backend.schemas.content import SessionView


class LangSmithService:
    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.langsmith_api_key)

    @property
    def tracing_enabled(self) -> bool:
        return self.configured and self.settings.langsmith_tracing

    def _get_client(self) -> Client:
        if not self.configured:
            raise ValueError("LangSmith API key is not configured")
        if self._client is None:
            self._client = Client(
                api_key=self.settings.langsmith_api_key,
                api_url=self.settings.langsmith_endpoint,
                workspace_id=self.settings.langsmith_workspace_id,
            )
        return self._client

    def export_approved_session(self, session: SessionView) -> dict[str, Any]:
        if not session.content_approved or not session.approved_content:
            raise ValueError("Approve content before exporting it to LangSmith")
        if session.langsmith_export.get("status") == "exported":
            return dict(session.langsmith_export)

        client = self._get_client()
        datasets = list(client.list_datasets(dataset_name=self.settings.langsmith_dataset))
        dataset = datasets[0] if datasets else client.create_dataset(
            dataset_name=self.settings.langsmith_dataset,
            description="Human-approved Ekmind content examples",
        )
        example_id = uuid5(NAMESPACE_URL, f"ekmind:{session.workspace_id}:{session.session_id}")
        angle = session.selected_angle.model_dump(mode="json") if session.selected_angle else None
        example = client.create_example(
            example_id=example_id,
            dataset_id=dataset.id,
            inputs={
                "topic": session.request.topic,
                "objective": session.request.objective,
                "audience": session.request.audience,
                "tone": session.request.tone,
                "research_mode": str(session.request.research_mode),
                "selected_angle": angle,
            },
            outputs={"approved_content": session.approved_content},
            metadata={
                "session_id": session.session_id,
                "workspace_id": session.workspace_id,
                "revision_count": session.revision_count,
                "similarity_score": session.similarity_score,
                "source_count": len(session.research_sources),
            },
            split="production-approved",
        )
        return {
            "status": "exported",
            "dataset": self.settings.langsmith_dataset,
            "dataset_id": str(dataset.id),
            "example_id": str(example.id),
        }
