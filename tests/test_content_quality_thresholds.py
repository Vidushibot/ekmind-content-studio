from backend.schemas.content import CritiqueResult
from backend.services.evaluation_service import content_quality_passes
from backend.services.evaluation_service import session_metrics
from types import SimpleNamespace


def critique(**overrides):
    values = {
        "clarity": 8,
        "value": 7,
        "engagement": 7,
        "tone": 8,
        "originality": 6,
        "voice_match": 7,
        "audience_relevance": 8,
        "strengths": [],
        "weaknesses": [],
        "required_changes": [],
    }
    values.update(overrides)
    return CritiqueResult(**values)


def test_content_quality_threshold_boundaries_pass():
    assert content_quality_passes(critique())


def test_each_content_quality_threshold_can_require_revision():
    assert not content_quality_passes(critique(clarity=7.99))
    assert not content_quality_passes(critique(value=6.99))
    assert not content_quality_passes(critique(engagement=6.99))
    assert not content_quality_passes(critique(tone=7.99))
    assert not content_quality_passes(critique(originality=5.99))
    assert not content_quality_passes(critique(voice_match=6.99))
    assert not content_quality_passes(critique(audience_relevance=7.99))


def test_factual_correctness_target_is_seven_when_research_is_enabled():
    view = SimpleNamespace(
        planner=SimpleNamespace(requires_research=True), research_sources=[], retrieval_evaluation={},
        content_approved=True, unsupported_claims=[], claim_assessments=[], faithfulness_score=None,
        critique=None, draft_versions=[], approved_content="Approved", similarity_score=0,
        decision_history=[], revision_count=0, max_revisions=2, angle_approved=True,
        evaluation_groups={"Trajectory": "PASS"}, status="PUBLISH_READY",
    )
    factual = next(row for row in session_metrics(view) if row["metric"] == "Factual Correctness")
    assert factual["target"] == ">= 7/10"
    assert factual["status"] == "PASS"


def test_factual_correctness_is_not_applicable_without_research():
    view = SimpleNamespace(
        planner=SimpleNamespace(requires_research=False), research_sources=[], retrieval_evaluation={},
        content_approved=True, unsupported_claims=[], claim_assessments=[], faithfulness_score=None,
        critique=None, draft_versions=[], approved_content="Approved", similarity_score=0,
        decision_history=[], revision_count=0, max_revisions=2, angle_approved=True,
        evaluation_groups={"Trajectory": "PASS"}, status="PUBLISH_READY",
    )
    factual = next(row for row in session_metrics(view) if row["metric"] == "Factual Correctness")
    assert factual["value"] == "NOT_APPLICABLE"
    assert factual["status"] == "NOT_APPLICABLE"
    assert factual["target"] == "Research only"
