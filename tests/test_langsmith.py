from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.config import Settings
from backend.schemas.content import GenerateRequest
from backend.services.content_service import ContentService
from backend.services.langsmith_service import LangSmithService


class FakeLangSmithClient:
    def __init__(self) -> None:
        self.dataset = SimpleNamespace(id=uuid4())
        self.created = []

    def list_datasets(self, **kwargs):
        return []

    def create_dataset(self, **kwargs):
        return self.dataset

    def create_example(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id=kwargs["example_id"])


def test_langsmith_export_requires_approved_content():
    view = ContentService().create(GenerateRequest(topic="A governed workflow"))
    exporter = LangSmithService(Settings(langsmith_api_key="test", langsmith_tracing=True), FakeLangSmithClient())
    with pytest.raises(ValueError, match="Approve content"):
        exporter.export_approved_session(view)


def test_langsmith_export_uses_deterministic_example_and_safe_metadata():
    service = ContentService()
    view = service.create(GenerateRequest(topic="A governed workflow"))
    view.selected_angle = view.candidate_angles[0]
    view.angle_approved = True
    view.content_approved = True
    view.approved_content = "A human-approved example."
    fake = FakeLangSmithClient()
    exporter = LangSmithService(Settings(langsmith_api_key="test", langsmith_tracing=True), fake)

    result = exporter.export_approved_session(view)

    assert result["status"] == "exported"
    assert UUID(result["example_id"])
    assert fake.created[0]["metadata"]["session_id"] == view.session_id
    assert "api_key" not in str(fake.created[0]).lower()
