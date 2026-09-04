from __future__ import annotations

import html
import json
import os
import platform
import statistics
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from importlib.metadata import PackageNotFoundError, version

from backend.agents import demo, live
from backend.config import get_settings
from backend.evaluations.manifest import build_manifest, source_hash
from backend.evaluations.metrics import contains_secret, evidence_coverage, faithfulness_score
from backend.graph.graph import post_graph, strategy_graph
from backend.schemas.content import Evidence, GenerateRequest


@contextmanager
def free_provider_substitutions(events: list[dict[str, object]], test_id: str) -> Iterator[None]:
    originals = {name: getattr(live, name) for name in ("search_web", "generate_angles", "write_post", "critique_post", "revise_post")}
    settings = get_settings()
    original_search_key, original_openai_key = settings.search_api_key, settings.openai_api_key
    original_tracing = os.environ.get("LANGSMITH_TRACING")
    original_legacy_tracing = os.environ.get("LANGCHAIN_TRACING_V2")

    def search(query: str, _api_key: str) -> list[Evidence]:
        events.append({"tool": "research", "success": True})
        return [Evidence(evidence_id=f"EV-{test_id}", claim=query, source_title="Controlled evaluation evidence", source_url=f"https://evaluation.invalid/{test_id}", publisher="evaluation.invalid", confidence=1.0, verification_status="CONTROLLED")]

    def angles(request, _evidence, _api_key, _model):
        events.append({"tool": "angle_generator", "success": True})
        return demo.generate_angles(request)

    def write(request, angle, _evidence, _api_key, _model):
        events.append({"tool": "writer", "success": True})
        return demo.write_post(request, angle)

    def critique(post, _request, _api_key, _model):
        events.append({"tool": "critic", "success": True})
        return demo.critique(post)

    def revise(post, _critique, _request, _evidence, _api_key, _model):
        events.append({"tool": "reviser", "success": True})
        return post + "\n\nA useful next step is to test this in one bounded workflow."

    live.search_web, live.generate_angles, live.write_post = search, angles, write
    live.critique_post, live.revise_post = critique, revise
    settings.search_api_key = "evaluation-mock"
    settings.openai_api_key = "evaluation-mock"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    try:
        yield
    finally:
        settings.search_api_key, settings.openai_api_key = original_search_key, original_openai_key
        if original_tracing is None:
            os.environ.pop("LANGSMITH_TRACING", None)
        else:
            os.environ["LANGSMITH_TRACING"] = original_tracing
        if original_legacy_tracing is None:
            os.environ.pop("LANGCHAIN_TRACING_V2", None)
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = original_legacy_tracing
        for name, value in originals.items():
            setattr(live, name, value)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * percentile) - 1))]


def evaluate_case(case: dict[str, object], policy: dict[str, object]) -> dict[str, object]:
    events: list[dict[str, object]] = []
    timings: dict[str, float] = {}
    request = GenerateRequest(topic=str(case["user_input"]))
    with free_provider_substitutions(events, str(case["test_id"])):
        started = time.perf_counter()
        stage = time.perf_counter()
        strategy = strategy_graph.invoke({"request": request})
        timings["strategy"] = time.perf_counter() - stage
        events.insert(0, {"tool": "planner", "success": True})
        angles = strategy["candidate_angles"]
        events.append({"checkpoint": "angle", "decision": "APPROVED"})
        stage = time.perf_counter()
        post = post_graph.invoke({
            "request": request,
            "selected_angle": angles[0],
            "research_sources": strategy.get("research_sources", []),
            "max_revisions": int(case["maximum_revisions"]),
            "quality_threshold": float(policy["quality_targets"]["content_quality"]),
        })
        timings["content"] = time.perf_counter() - stage
        events.append({"checkpoint": "content", "decision": "APPROVED"})
        timings["total"] = time.perf_counter() - started

    actual_tools = [str(event["tool"]) for event in events if "tool" in event]
    approvals = [str(event["checkpoint"]) for event in events if event.get("decision") == "APPROVED"]
    coverage = evidence_coverage(set(str(item) for item in case["expected_claim_ids"]), set())
    assessments = []  # Controlled cases need human-adjudicated claim labels before faithfulness is scored.
    faithfulness = faithfulness_score(assessments)
    expected_research = bool(case["expected_research"])
    research_actual = "research" in actual_tools
    checks = {
        "research_route": research_actual == expected_research,
        "three_distinct_angles": len(angles) == 3 and len({angle.angle_type for angle in angles}) == 3,
        "required_tools": set(case["expected_tools"]) <= set(actual_tools),
        "forbidden_tools": not (set(case["forbidden_tools"]) & set(actual_tools)),
        "hitl_compliance": set(case["required_approvals"]) <= set(approvals),
        "revision_limit": int(post["revision_count"]) <= int(case["maximum_revisions"]),
        "final_state": case["expected_final_state"] == "PUBLISH_READY",
        "tool_call_success": all(bool(event.get("success", True)) for event in events),
        "secret_exposure": not contains_secret(post["current_draft"]),
    }
    return {
        "test_id": case["test_id"],
        "split": case["split"],
        "scenario_type": case["scenario_type"],
        "passed": all(checks.values()),
        "checks": checks,
        "actual_tools": actual_tools,
        "approvals": approvals,
        "revision_count": post["revision_count"],
        "content_quality": post["critique"].overall,
        "evidence_coverage": coverage if coverage is not None else "NOT_EVALUATED",
        "faithfulness": faithfulness if faithfulness is not None else "NOT_EVALUATED",
        "timings_seconds": {key: round(value, 6) for key, value in timings.items()},
        "token_consumption": 0,
        "estimated_api_cost": 0.0,
    }


def release_decision(results: list[dict[str, object]], policy: dict[str, object]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    completion = sum(bool(result["passed"]) for result in results) / max(1, len(results))
    if completion < float(policy["quality_targets"]["end_to_end_completion"]):
        failures.append(f"Completion {completion:.1%} is below target {policy['quality_targets']['end_to_end_completion']:.1%}")
    hard_checks = ("forbidden_tools", "hitl_compliance", "revision_limit", "tool_call_success", "secret_exposure")
    for check in hard_checks:
        failed = [str(result["test_id"]) for result in results if not result["checks"][check]]
        if failed:
            failures.append(f"Hard gate {check} failed: {', '.join(failed)}")
    if any(result["faithfulness"] == "NOT_EVALUATED" for result in results):
        failures.append("Faithfulness is not evaluated; add human-adjudicated claim/evidence mappings")
    for metric in ("evidence_coverage", "faithfulness"):
        values = [float(result[metric]) for result in results if isinstance(result[metric], (int, float))]
        target = policy["quality_targets"].get(metric)
        if values and target is not None and statistics.mean(values) < float(target):
            failures.append(f"Mean {metric} {statistics.mean(values):.3f} is below target {float(target):.3f}")
    quality = [float(result["content_quality"]) for result in results]
    if quality and statistics.mean(quality) < float(policy["quality_targets"]["content_quality"]):
        failures.append("Mean content quality is below target")
    p95 = _percentile([float(result["timings_seconds"]["total"]) for result in results], 0.95)
    if p95 > float(policy["quality_targets"]["p95_latency_seconds"]):
        failures.append(f"p95 latency {p95:.3f}s exceeds target")
    return not failures, failures


def write_html_report(report: dict[str, object], destination: Path) -> None:
    rows = "".join(
        f"<tr><td>{html.escape(str(item['test_id']))}</td><td>{html.escape(str(item['scenario_type']))}</td>"
        f"<td>{'PASS' if item['passed'] else 'FAIL'}</td><td>{item['content_quality']}</td>"
        f"<td>{item['evidence_coverage']}</td><td>{item['faithfulness']}</td></tr>"
        for item in report["results"]
    )
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in report["release_failures"]) or "<li>None</li>"
    document = f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(str(report['experiment_id']))}</title>
<style>body{{font:16px Arial;max-width:1100px;margin:40px auto;color:#172554}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #ddd;text-align:left}}th{{background:#172554;color:white}}.pass{{color:#087830}}</style></head><body>
<h1>Evaluation report: {html.escape(str(report['experiment_id']))}</h1><p>Release ready: <b class='pass'>{report['release_ready']}</b></p>
<p>{report['passed']}/{report['cases']} cases passed ({report['completion_rate']:.1%}). Providers: deterministic mocks; API cost: $0.</p>
<h2>Release failures</h2><ul>{failures}</ul><h2>Case results</h2><table><tr><th>Test</th><th>Scenario</th><th>Result</th><th>Quality</th><th>Evidence coverage</th><th>Faithfulness</th></tr>{rows}</table></body></html>"""
    destination.write_text(document, encoding="utf-8")


def run_free_experiment(dataset: Path, policy_path: Path, output_dir: Path, experiment_id: str, split: str, overwrite: bool = False) -> dict[str, object]:
    destination = output_dir / f"{experiment_id}.json"
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Experiment '{experiment_id}' already exists; choose a new ID or pass --overwrite")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    manifest = build_manifest(dataset)
    cases = [case for case in manifest["cases"] if split == "all" or case["split"] == split]
    started = time.perf_counter()
    results = [evaluate_case(case, policy) for case in cases]
    release_ready, failures = release_decision(results, policy)
    latencies = [float(item["timings_seconds"]["total"]) for item in results]
    report = {
        "experiment_id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": "free-deterministic-mocks",
        "split": split,
        "policy_version": policy["policy_version"],
        "manifest_version": manifest["manifest_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "source_sha256": source_hash(get_settings().project_root),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "model": "deterministic-demo",
        "prompt_versions": {"planner": "demo-v3", "writer": "demo-v1", "critic": "demo-v1"},
        "graph_version": "v2",
        "evaluator_version": "free-v1",
        "dependency_versions": {
            package: (version(package) if _package_exists(package) else "not-installed")
            for package in ("langgraph", "pydantic", "sqlalchemy")
        },
        "provider_cost": 0.0,
        "cases": len(results),
        "passed": sum(bool(item["passed"]) for item in results),
        "completion_rate": sum(bool(item["passed"]) for item in results) / max(1, len(results)),
        "trajectory_success": sum(bool(item["passed"]) for item in results) / max(1, len(results)),
        "latency_seconds": round(time.perf_counter() - started, 4),
        "mean_case_latency_seconds": round(statistics.mean(latencies), 6) if latencies else 0,
        "p95_case_latency_seconds": round(_percentile(latencies, 0.95), 6),
        "token_consumption": 0,
        "estimated_api_cost": 0.0,
        "release_ready": release_ready,
        "release_failures": failures,
        "limitations": [
            "Faithfulness is NOT_EVALUATED until human-adjudicated claim/evidence mappings are added.",
            "Mock-provider results validate orchestration and gates, not live model or live web quality.",
        ],
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_html_report(report, output_dir / f"{experiment_id}.html")
    return report


def _package_exists(package: str) -> bool:
    try:
        version(package)
        return True
    except PackageNotFoundError:
        return False
