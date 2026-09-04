from backend.agents.demo import generate_angles, plan
from backend.schemas.content import GenerateRequest, ResearchMode
from backend.services.content_service import ContentService


def test_exactly_three_distinct_angles():
    angles = generate_angles(GenerateRequest(topic="Responsible AI adoption"))
    assert len(angles) == 3
    assert len({angle.angle_type for angle in angles}) == 3


def test_research_decision():
    assert plan(GenerateRequest(topic="Latest SAP capabilities")).requires_research
    assert not plan(GenerateRequest(topic="My reflection on leadership", research_mode="Skip")).requires_research


def test_hitl_and_revision_limit(tmp_path, monkeypatch):
    service = ContentService()
    view = service.create(GenerateRequest(topic="Human-centered AI"))
    assert view.status == "AWAITING_ANGLE_APPROVAL"
    assert view.current_draft is None
    view = service.approve_angle(view.session_id, __import__("backend.schemas.content", fromlist=["ApprovalRequest"]).ApprovalRequest(angle_id=view.candidate_angles[0].angle_id))
    assert view.angle_approved and view.status == "AWAITING_CONTENT_APPROVAL"
    assert view.revision_count <= 2
    assert not view.content_approved


def test_repeated_angle_approval_is_idempotent():
    service = ContentService()
    view = service.create(GenerateRequest(topic="Governed AI workflows"))
    approval_type = __import__("backend.schemas.content", fromlist=["ApprovalRequest"]).ApprovalRequest
    approval = approval_type(angle_id=view.candidate_angles[0].angle_id)
    first = service.approve_angle(view.session_id, approval)
    second = service.approve_angle(view.session_id, approval)
    assert second.status == "AWAITING_CONTENT_APPROVAL"
    assert second.current_draft == first.current_draft
    assert second.revision_count == first.revision_count


def test_saved_sessions_can_be_reopened_for_evaluation():
    service = ContentService()
    created = service.create(GenerateRequest(topic="Evaluation session persistence", research_mode=ResearchMode.SKIP))
    sessions = service.list_sessions()
    assert any(item.session_id == created.session_id for item in sessions)
