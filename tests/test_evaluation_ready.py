import json
from collections import Counter
from pathlib import Path

import pytest

from backend.evaluations.free_runner import run_free_experiment
from backend.evaluations.calibration import calibration_report
from backend.evaluations.manifest import build_manifest
from backend.evaluations.metrics import assess_faithfulness, classify_sentence, evidence_coverage, faithfulness_score
from backend.schemas.content import ClaimReviewRequest, Evidence, GenerateRequest, ResearchMode
from backend.services.content_service import ContentService


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT.parent / "Ekmind_AI_Content_Studio_Golden_Dataset.xlsx"
POLICY = ROOT / "evaluation_data" / "evaluation_policy.json"


def test_manifest_is_stratified_and_versioned():
    manifest = build_manifest(DATASET)
    assert len(manifest["cases"]) == 40
    assert len(manifest["dataset_sha256"]) == 64
    assert Counter(case["split"] for case in manifest["cases"]) == {
        "development": 24,
        "validation": 8,
        "hidden_test": 8,
    }
    assert all(case["critical_gate"] and case["expected_behavior"] for case in manifest["cases"])


def test_evidence_coverage_uses_labeled_claim_ids():
    assert evidence_coverage({"C1", "C2"}, {"C1"}) == 0.5


def test_deterministic_faithfulness_rejects_missing_number():
    evidence = [{"evidence_id": "EV1", "text": "Adoption increased by 12% in the controlled study."}]
    assessments = assess_faithfulness(["Adoption increased by 45%."], evidence)
    assert assessments[0].classification != "SUPPORTED"
    assert faithfulness_score(assessments) == 0.0


def test_passage_matching_partial_credit_and_sentence_types():
    evidence = [{
        "evidence_id": "EV1",
        "text": "The product facilitates ongoing feedback. It includes AI-driven capabilities for performance decisions.",
        "source_title": "Official documentation",
        "source_url": "https://example.com/docs",
    }]
    assessments = assess_faithfulness(["The product includes AI-driven capabilities for performance decisions."], evidence)
    assert assessments[0].classification == "SUPPORTED"
    assert assessments[0].best_passage
    assert assessments[0].source_url == "https://example.com/docs"
    assert classify_sentence("Explore the documentation for more information.") == "CALL_TO_ACTION"
    assert classify_sentence("Could this help your team?") == "QUESTION"
    assert faithfulness_score([
        {"classification": "SUPPORTED"},
        {"classification": "PARTIALLY_SUPPORTED"},
    ]) == 7.5


def test_sap_style_paraphrase_no_longer_scores_zero():
    evidence = [{
        "evidence_id": "SAP1",
        "text": "The SAP SuccessFactors Performance & Goals solution helps you drive peak performance, give real-time feedback, and make intelligent skills-based decisions.",
        "source_title": "SAP documentation",
        "source_url": "https://example.com/sap",
    }]
    claims = [
        "SAP SuccessFactors Performance & Goals offers tools for real-time feedback and AI-driven insights.",
        "Its capabilities support organizations in driving a high-performance culture.",
    ]
    assessments = assess_faithfulness(claims, evidence)
    assert faithfulness_score(assessments) > 0
    assert all(item.classification != "CONTRADICTED" for item in assessments)


def test_human_claim_review_persists_across_reevaluation():
    service = ContentService()
    view = service.create(GenerateRequest(topic="Reflective leadership", research_mode=ResearchMode.SKIP))
    view.planner.requires_research = True
    view.status = "AWAITING_CONTENT_APPROVAL"
    view.current_draft = "Research shows adoption increased by 45%."
    view.research_sources = [Evidence(claim="Research shows adoption increased by 12%.", source_title="Study", source_url="https://example.com/study", publisher="example.com", confidence=.9, verification_status="RETRIEVED")]
    service._save(view)
    view = service.reevaluate_content(view.session_id)
    assert view.unsupported_claims
    claim = view.claim_assessments[0]["claim"]
    view = service.review_claim(view.session_id, ClaimReviewRequest(claim=claim, classification="SUPPORTED", reason="Human verified against the full source."))
    view = service.reevaluate_content(view.session_id)
    assert view.claim_assessments[0]["effective_classification"] == "SUPPORTED"
    assert view.unsupported_claims == []


def test_judge_calibration_rejects_material_false_pass():
    report = calibration_report([{
        "human_label": "UNSUPPORTED",
        "judge_label": "SUPPORTED",
        "material": True,
        "human_score": 0,
        "judge_score": 10,
    }])
    assert report["status"] == "FAIL"
    assert report["material_false_passes"] == 1


def test_open_web_session_metrics_exclude_precision_and_recall():
    service = ContentService()
    view = service.create(GenerateRequest(topic="A reflective leadership post", research_mode=ResearchMode.SKIP))
    view.planner.requires_research = True
    view.research_sources = [
        Evidence(
            evidence_id=f"EV-{index}",
            claim="Research shows adoption increased by 12% in the controlled study.",
            source_title="Controlled study",
            source_url=f"https://example.com/{index}",
            publisher="example.com",
            confidence=.9,
            verification_status="RETRIEVED",
            retrieval_rank=index,
            relevance_score=.9,
            relevance_label="RELEVANT",
        )
        for index in range(1, 6)
    ]
    service._evaluate_retrieval(view)
    assert "precision_at_5" not in view.retrieval_evaluation
    assert "recall_at_5" not in view.retrieval_evaluation
    unsupported = service._evaluate_faithfulness(view, "Research shows adoption increased by 12% in the controlled study.")
    assert unsupported == []
    assert view.faithfulness_score == 10.0


def test_free_runner_is_zero_cost_reproducible_and_immutable(tmp_path):
    report = run_free_experiment(DATASET, POLICY, tmp_path, "free_validation_v1", "validation")
    assert report["cases"] == 8
    assert report["estimated_api_cost"] == 0
    assert report["token_consumption"] == 0
    assert report["passed"] == 8
    assert report["release_ready"] is False
    assert any("Faithfulness" in reason for reason in report["release_failures"])
    assert len(report["dataset_sha256"]) == 64
    assert len(report["source_sha256"]) == 64
    assert (tmp_path / "free_validation_v1.html").exists()
    persisted = json.loads((tmp_path / "free_validation_v1.json").read_text(encoding="utf-8"))
    assert persisted["evaluation_mode"] == "free-deterministic-mocks"
    with pytest.raises(FileExistsError):
        run_free_experiment(DATASET, POLICY, tmp_path, "free_validation_v1", "validation")
