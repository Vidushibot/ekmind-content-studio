from __future__ import annotations

from collections import Counter
from typing import Iterable


def calibration_report(judgments: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(judgments)
    adjudicated = [row for row in rows if row.get("human_label") not in (None, "") and row.get("judge_label") not in (None, "")]
    if not adjudicated:
        return {"status": "NOT_EVALUATED", "cases": 0}
    agreement = sum(str(row["human_label"]) == str(row["judge_label"]) for row in adjudicated) / len(adjudicated)
    material = [row for row in adjudicated if bool(row.get("material", False))]
    false_passes = sum(str(row["human_label"]) != "SUPPORTED" and str(row["judge_label"]) == "SUPPORTED" for row in material)
    numeric = [row for row in adjudicated if isinstance(row.get("human_score"), (int, float)) and isinstance(row.get("judge_score"), (int, float))]
    mae = sum(abs(float(row["human_score"]) - float(row["judge_score"])) for row in numeric) / len(numeric) if numeric else None
    return {
        "status": "PASS" if agreement >= 0.85 and false_passes == 0 and (mae is None or mae <= 1.0) else "FAIL",
        "cases": len(adjudicated),
        "agreement": round(agreement, 3),
        "material_false_passes": false_passes,
        "mean_absolute_score_error": round(mae, 3) if mae is not None else "NOT_EVALUATED",
        "human_label_distribution": dict(Counter(str(row["human_label"]) for row in adjudicated)),
    }
