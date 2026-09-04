import re
from difflib import SequenceMatcher
from typing import Any

FACT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%|\baccording to\b|\bresearch shows\b", re.I)

CONTENT_QUALITY_THRESHOLDS = {
    "clarity": 8.0,
    "value": 7.0,
    "engagement": 7.0,
    "tone": 8.0,
    "originality": 6.0,
    "voice_match": 7.0,
    "audience_relevance": 8.0,
}


def content_quality_passes(critique: Any) -> bool:
    return bool(critique) and all(float(getattr(critique, field)) >= threshold for field, threshold in CONTENT_QUALITY_THRESHOLDS.items())


def extract_material_claims(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if FACT_PATTERN.search(s)]


def unsupported_claims(text: str, verified: list[str]) -> list[str]:
    return [c for c in extract_material_claims(text) if not any(SequenceMatcher(None, c.casefold(), v.casefold()).ratio() >= .65 for v in verified)]


def similarity(text: str, prior: list[str]) -> float:
    return round(max((SequenceMatcher(None, text.casefold(), p.casefold()).ratio() for p in prior), default=0), 3)


def human_edit_percentage(draft: str, approved: str) -> float:
    return round((1 - SequenceMatcher(None, draft, approved).ratio()) * 100, 2)


def session_metrics(view: Any) -> list[dict[str, object]]:
    """Build an honest, stage-aware evaluation report for one content session."""
    rows: list[dict[str, object]] = []

    def add(group: str, metric: str, value: object, status: str, approach: str, target: str = "") -> None:
        rows.append({"group": group, "metric": metric, "value": value, "status": status, "target": target, "approach": approach})

    research_required = bool(view.planner.requires_research)
    sources = view.research_sources
    retrieval_status = "NOT_REQUIRED" if not research_required else ("PASS" if sources else "PENDING")
    retrieval = view.retrieval_evaluation or {}
    relevance = retrieval.get("retrieval_relevance", "NOT_EVALUATED" if research_required else "NOT_REQUIRED")
    relevance_status = "PASS" if isinstance(relevance, (int, float)) and relevance >= .5 else ("REVISE" if isinstance(relevance, (int, float)) else str(relevance))
    add("1. Retrieval Quality", "Retrieval Relevance", relevance, relevance_status, "Open-web provider score + deterministic query overlap; heuristic, not human-calibrated", ">= 0.50")

    claim_rows = view.claim_assessments or []
    effective = [str(row.get("effective_classification") or row.get("classification")) for row in claim_rows]
    evaluated = [value for value in effective if value in {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"}]
    support_points = sum(1.0 if value == "SUPPORTED" else .5 if value == "PARTIALLY_SUPPORTED" else 0.0 for value in evaluated)
    unresolved_material = sum(bool(row.get("material")) and str(row.get("effective_classification") or row.get("classification")) == "NEEDS_HUMAN_REVIEW" for row in claim_rows)
    if not research_required:
        coverage = "NOT_APPLICABLE"
        coverage_status = "NOT_APPLICABLE"
        coverage_target = "Research only"
    else:
        coverage = round(support_points / len(evaluated), 3) if evaluated else ("NOT_REQUIRED" if view.content_approved else "PENDING")
        coverage_status = "REVIEW" if unresolved_material else ("PASS" if isinstance(coverage, (int, float)) and coverage >= .9 else ("FAIL" if isinstance(coverage, (int, float)) else str(coverage)))
        coverage_target = ">= 0.90"
    add("1. Retrieval Quality", "Evidence Coverage", coverage, coverage_status, "Generated factual claims supported by retrieved passages", coverage_target)

    gate_ready = bool(view.content_approved or view.unsupported_claims)
    unsupported = len(view.unsupported_claims)
    gate_score = 10.0 if gate_ready and unsupported == 0 else (0.0 if unsupported else "Pending")
    hard_gate_status = "PASS" if gate_score == 10.0 else ("FAIL" if gate_score == 0.0 else "PENDING")
    if research_required:
        factual_value = gate_score
        factual_status = "PASS" if isinstance(gate_score, (int, float)) and gate_score >= 7 else ("FAIL" if isinstance(gate_score, (int, float)) else "PENDING")
        factual_target = ">= 7/10"
    else:
        factual_value = "NOT_APPLICABLE"
        factual_status = "NOT_APPLICABLE"
        factual_target = "Research only"
    add("2. Factual & Grounding", "Factual Correctness", factual_value, factual_status, "Hard gate against verified material claims when research is enabled", factual_target)
    faithfulness = view.faithfulness_score
    if not research_required:
        faith_value = "NOT_APPLICABLE"
        faith_status = "NOT_APPLICABLE"
        grounded_value = "NOT_APPLICABLE"
        grounded_status = "NOT_APPLICABLE"
        grounding_target = "Research only"
    else:
        faith_value = faithfulness if faithfulness is not None else ("NOT_REQUIRED" if view.content_approved and not claim_rows else "PENDING")
        faith_status = "REVIEW" if unresolved_material else ("PASS" if isinstance(faith_value, (int, float)) and faith_value >= 9 else ("FAIL" if isinstance(faith_value, (int, float)) else str(faith_value)))
        grounded_value = faith_value if isinstance(faith_value, (int, float)) else gate_score
        grounded_status = faith_status if isinstance(faith_value, (int, float)) else hard_gate_status
        grounding_target = ">= 9/10"
    add("2. Factual & Grounding", "Groundedness", grounded_value, grounded_status, "Claim-level deterministic comparison against retrieved web passages", grounding_target)
    add("2. Factual & Grounding", "Faithfulness", faith_value, faith_status, "Claim-level deterministic evidence check; human/LLM calibration still recommended", grounding_target)
    if research_required:
        unsupported_value = unsupported if gate_ready else "Pending"
        unsupported_status = hard_gate_status
        unsupported_target = "0"
    else:
        unsupported_value = "NOT_APPLICABLE"
        unsupported_status = "NOT_APPLICABLE"
        unsupported_target = "Research only"
    add("2. Factual & Grounding", "Unsupported Claims", unsupported_value, unsupported_status, "Deterministic material-claim gate", unsupported_target)

    critique = view.critique
    quality = [
        ("Clarity", "clarity", "LLM judge", 8.0),
        ("Value", "value", "LLM judge", 7.0),
        ("Engagement", "engagement", "LLM judge; clickbait is not rewarded", 7.0),
        ("Tone", "tone", "LLM judge against requested tone", 8.0),
        ("Originality", "originality", "LLM judge + approved-library similarity", 6.0),
        ("Voice Match", "voice_match", "LLM judge against voice profile", 7.0),
        ("Audience Relevance", "audience_relevance", "LLM judge", 8.0),
    ]
    for metric, field, approach, threshold in quality:
        value = getattr(critique, field) if critique else "Pending"
        if metric == "Originality" and critique and view.content_approved:
            value = round((float(value) + (1 - view.similarity_score) * 10) / 2, 2)
        add("3. Content Quality", metric, value, "PASS" if isinstance(value, (int, float)) and value >= threshold else ("REVISE" if isinstance(value, (int, float)) else "PENDING"), approach, f">= {threshold:g}/10")

    initial = view.draft_versions[0] if view.draft_versions else ""
    edit = human_edit_percentage(initial, view.approved_content) if initial and view.approved_content else "Pending"
    rejected = [d for d in view.decision_history if d.get("decision") == "REJECTED"]
    first_draft = bool(view.content_approved and view.revision_count == 0 and edit == 0)
    add("4. Human Quality", "Human Edit %", edit, "RECORDED" if edit != "Pending" else "PENDING", "Deterministic diff: initial AI draft vs approved final")
    add("4. Human Quality", "First Draft Approval", first_draft if view.content_approved else "Pending", "PASS" if first_draft else ("RECORDED" if view.content_approved else "PENDING"), "Deterministic")
    add("4. Human Quality", "Regeneration Count", len(rejected), "RECORDED", "Deterministic rejected-stage count")
    add("4. Human Quality", "Revision Count", view.revision_count, "PASS" if view.revision_count <= view.max_revisions else "FAIL", "Deterministic", f"<= {view.max_revisions}")

    research_ok = (not research_required) or bool(sources)
    hitl_ok = not view.content_approved or view.angle_approved
    retries_ok = view.revision_count <= view.max_revisions
    path_ok = research_ok and hitl_ok and retries_ok
    tool_selection = "PASS" if research_ok else "FAIL"
    tool_success = "PASS" if view.evaluation_groups.get("Trajectory") != "FAIL" else "FAIL"
    efficiency = round(max(0.0, 10.0 - view.revision_count * 2.0 - len(rejected)), 1)
    completed = view.status in {"PUBLISH_READY", "AWAITING_SLIDE_APPROVAL", "SLIDES_APPROVED", "AWAITING_VIDEO_APPROVAL", "DONE"}
    add("5. Trajectory", "Correct Agent Path", path_ok, "PASS" if path_ok else "FAIL", "Expected vs actual workflow state")
    add("5. Trajectory", "Tool Selection", tool_selection, tool_selection, "Research tool selected when required")
    add("5. Trajectory", "Tool Call Success", tool_success, tool_success, "Recorded graph/tool outcome")
    add("5. Trajectory", "Step Efficiency", efficiency, "PASS" if efficiency >= 7 else "REVISE", "Penalizes revisions and regenerations", ">= 7/10")
    add("5. Trajectory", "HITL Compliance", hitl_ok, "PASS" if hitl_ok else "FAIL", "Hard gate: mandatory approvals", "Required")
    add("5. Trajectory", "Retry Behaviour", retries_ok, "PASS" if retries_ok else "FAIL", "Bounded retry check", f"<= {view.max_revisions}")
    add("5. Trajectory", "Goal Completion", completed, "PASS" if completed else "IN_PROGRESS", "Valid requested outcome reached")
    return rows
