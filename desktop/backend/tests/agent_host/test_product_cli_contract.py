from __future__ import annotations

from pathlib import Path


def test_product_cli_uses_agent_v1_only():
    source = (Path(__file__).parents[4] / "scripts" / "notemeld-agent.py").read_text()
    assert "/sessions" in source
    assert "/turns/" in source
    assert "/chat/free" not in source
    assert "/chat/ask" not in source
    assert "--format" in source
    assert "/model" in source
    assert "/resume" in source
    assert "/cancel" in source
