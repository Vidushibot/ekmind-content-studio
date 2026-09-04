import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.agents.demo import generate_angles, plan
from backend.evaluations.dataset_loader import load_golden_dataset, validate_distribution
from backend.schemas.content import GenerateRequest


def run_experiment(dataset: Path, output_dir: Path, experiment_id: str) -> dict:
    rows = load_golden_dataset(dataset); validate_distribution(rows); started = time.perf_counter(); passed = 0; results = []
    for row in rows:
        request = GenerateRequest(topic=str(row["User Input"])); planner = plan(request); angles = generate_angles(request)
        expected_research = str(row["Research Expected"]).casefold() == "yes"
        ok = len(angles) == 3 and len({a.angle_type for a in angles}) == 3 and planner.requires_research == expected_research
        passed += int(ok); results.append({"test_id": row["Test ID"], "passed": ok, "research_expected": expected_research, "research_actual": planner.requires_research})
    report = {"experiment_id": experiment_id, "created_at": datetime.now(timezone.utc).isoformat(), "model": "deterministic-demo", "prompt_version": "v1", "retrieval_k": 5, "graph_version": "v2", "cases": len(rows), "passed": passed, "trajectory_success": passed / len(rows), "latency_seconds": round(time.perf_counter()-started, 3), "token_consumption": 0, "estimated_api_cost": 0, "results": results}
    output_dir.mkdir(parents=True, exist_ok=True); (output_dir / f"{experiment_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8"); return report

