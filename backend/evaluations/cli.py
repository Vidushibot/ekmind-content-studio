from __future__ import annotations

import argparse
from pathlib import Path

from backend.config import get_settings
from backend.evaluations.free_runner import run_free_experiment
from backend.evaluations.manifest import write_manifest


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the zero-cost Ekmind evaluation suite")
    parser.add_argument("--experiment", required=True, help="Unique immutable experiment ID")
    parser.add_argument("--split", choices=("development", "validation", "hidden_test", "all"), default="validation")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    dataset = settings.project_root.parent / "Ekmind_AI_Content_Studio_Golden_Dataset.xlsx"
    policy = settings.project_root / "evaluation_data" / "evaluation_policy.json"
    write_manifest(dataset, settings.project_root / "evaluation_data" / "golden_manifest.json")
    report = run_free_experiment(dataset, policy, settings.project_root / "storage" / "experiments", args.experiment, args.split, args.overwrite)
    print(f"{report['passed']}/{report['cases']} passed; release_ready={report['release_ready']}; cost=$0")
    print(settings.project_root / "storage" / "experiments" / f"{args.experiment}.html")
    return 0 if report["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
