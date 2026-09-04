from pathlib import Path

from backend.evaluations.dataset_loader import EXPECTED, load_golden_dataset, validate_distribution


def test_golden_dataset_distribution():
    path = Path(__file__).resolve().parents[2] / "Ekmind_AI_Content_Studio_Golden_Dataset.xlsx"
    counts = validate_distribution(load_golden_dataset(path))
    assert dict(counts) == EXPECTED

