import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_cloud_product_docs_registry_is_validated():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/cloud/validate_product_docs.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    registry = json.loads((ROOT / "docs/new-product/config/feature-registry.json").read_text())
    assert len(registry["features"]) >= 9
    assert set(registry["bindings"]) <= set(registry["features"])
    assert registry["interaction_defaults"]["trigger"] == "click"
    assert registry["interaction_defaults"]["preview_behavior"]
    assert registry["interaction_defaults"]["explain_behavior"]
    assert registry["interaction_defaults"]["action"]
    assert registry["interaction_defaults"]["success"]
    assert registry["interaction_defaults"]["failure"]
    assert len(registry["database_details"]) >= 26
    assert {"organizations", "organization_members", "organization_preferences"} <= set(registry["database_details"])
    assert set(registry["architecture"]["cloud_control_plane"]) >= {"description", "modules"}
    login_page = (ROOT / "docs/new-product/pages/cloud/c01.html").read_text()
    assert 'type="email"' in login_page
    assert "用户名或邮箱" not in login_page
    page_script = (ROOT / "docs/new-product/assets/page.js").read_text()
    assert "bindExplainFeatures" in page_script
    explain_script = (ROOT / "docs/new-product/assets/product-docs.js").read_text()
    assert "event.target.closest('[data-feature-id]')" in explain_script
    page_script = (ROOT / "docs/new-product/assets/page.js").read_text()
    assert "event.target.closest('[data-feature-id]')" in page_script
    assert "defaults.action" in page_script and "defaults.failure" in page_script
    assert '../../assets/c03-live.js' in (ROOT / "docs/new-product/pages/cloud/c03.html").read_text()
    assert "data-mode=\"explain\"" in (ROOT / "docs/new-product/assets/portal.js").read_text()
