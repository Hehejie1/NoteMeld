from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "desktop" / "backend" / "tests" / "fixtures" / "n01-url-capability-baseline.json"
GENERATOR = ROOT / "scripts" / "desktop" / "generate_url_capability_baseline.py"


def test_url_capability_baseline_is_reproducible():
    before = BASELINE.read_bytes()
    subprocess.run([sys.executable, str(GENERATOR)], cwd=ROOT, check=True)
    assert BASELINE.read_bytes() == before


def test_url_capability_baseline_covers_registered_platforms_and_pipeline():
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    platforms = document["platforms"]
    assert [item["platform"] for item in platforms] == [
        "youtube", "bilibili", "tiktok", "kuaishou", "douyin", "wechat_channels", "local"
    ]
    assert all(item["capabilities"]["download"] for item in platforms)
    assert all(item["capabilities"]["screenshot"] for item in platforms)
    assert document["pipeline"] == {
        "subtitle_first": True,
        "download": True,
        "transcription": True,
        "screenshots": True,
        "web_fallback": True,
        "task_state": "desktop/backend/app/services/task_status_writer.py",
        "error_classification": "desktop/backend/app/enmus/exception.py",
    }
