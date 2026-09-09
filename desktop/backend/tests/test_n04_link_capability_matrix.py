from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "desktop/backend/tests/fixtures/n04-url-capability-matrix.json"
BASELINE = ROOT / "desktop/backend/tests/fixtures/n01-url-capability-baseline.json"


def test_n04_matrix_has_one_to_one_before_after_rows():
    matrix = json.loads(MATRIX.read_text())
    assert matrix["before"] == matrix["after"]
    assert len(matrix["before"]) == 8
    assert matrix["columns"] == [
        "platform", "kind", "subtitle_first", "download", "transcription", "screenshots",
        "multi_source_summary", "web_scrape", "task_state", "web_fallback", "error_classification",
    ]


def test_n04_matrix_covers_n01_platforms_and_pipeline():
    baseline = json.loads(BASELINE.read_text())
    matrix = json.loads(MATRIX.read_text())
    matrix_platforms = {row[0] for row in matrix["after"]}
    assert matrix_platforms == {item["platform"] for item in baseline["platforms"]} | {"web_link"}
    assert all(row[8:] == [True, True, True] for row in matrix["after"][:7])
