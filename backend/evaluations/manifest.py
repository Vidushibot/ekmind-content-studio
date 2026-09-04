from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from backend.evaluations.dataset_loader import CANONICAL_CATEGORIES, load_golden_dataset, validate_distribution


SPLIT_COUNTS = {
    "Happy Path": (12, 4, 4),
    "Edge Cases": (7, 3, 2),
    "Known Failures": (4, 1, 1),
    "Adversarial": (1, 0, 1),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hash(project_root: Path) -> str:
    digest = hashlib.sha256()
    paths = sorted((project_root / "backend").rglob("*.py"))
    paths += sorted((project_root / "evaluation_data").glob("*.json"))
    for path in paths:
        digest.update(str(path.relative_to(project_root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_manifest(dataset: Path) -> dict[str, object]:
    rows = load_golden_dataset(dataset)
    validate_distribution(rows)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        raw_category = str(row["Scenario Type"]).strip()
        category = CANONICAL_CATEGORIES.get(raw_category.casefold(), raw_category)
        grouped[category].append(row)

    cases = []
    for category, category_rows in grouped.items():
        development, validation, _ = SPLIT_COUNTS[category]
        for index, row in enumerate(category_rows):
            split = "development" if index < development else "validation" if index < development + validation else "hidden_test"
            research = str(row["Research Expected"]).strip().casefold() == "yes"
            expected_tools = ["research"] if research else []
            forbidden_tools = [] if research else ["research"]
            cases.append({
                "test_id": str(row["Test ID"]),
                "split": split,
                "scenario_type": category,
                "user_input": str(row["User Input"]),
                "expected_research": research,
                "expected_tools": expected_tools,
                "forbidden_tools": forbidden_tools,
                "required_approvals": ["angle", "content"],
                "maximum_revisions": 2,
                "expected_final_state": "PUBLISH_READY",
                "expected_behavior": str(row["Expected Behavior"]),
                "expected_result": str(row["Expected Result"]),
                "critical_gate": str(row["Critical Gate / Auto-Fail"]),
                "primary_eval_focus": str(row["Primary Eval Focus"]),
                "expected_evidence_ids": [],
                "expected_claim_ids": [],
            })
    return {
        "manifest_version": "1.0.0",
        "dataset_sha256": sha256_file(dataset),
        "dataset_path": dataset.name,
        "cases": cases,
    }


def write_manifest(dataset: Path, destination: Path) -> dict[str, object]:
    manifest = build_manifest(dataset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
