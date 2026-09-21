#!/usr/bin/env python3
"""Validate the product-docs feature registry against the current Cloud source."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "new-product"
REGISTRY = DOCS / "config" / "feature-registry.json"
CLOUD_APP = ROOT / "cloud" / "app.py"
CLOUD_DB = ROOT / "cloud" / "db.py"


def main() -> int:
    config = json.loads(REGISTRY.read_text())
    def page_source(page: str) -> str:
        group = "apps" if page.startswith("APP") else "cloud" if page.startswith(("A", "C")) else "desktop" if page.startswith("D") else "mobile"
        path = DOCS / "pages" / group / f"{page.lower()}.html"
        return path.read_text() if path.exists() else ""

    def referenced_assets(source: str) -> set[str]:
        return set(re.findall(r'<script[^>]+src="([^"]+)"', source))

    html = {page: page_source(page) for page in set(config["pages"]) | {feature["page"] for feature in config["features"].values()}}
    app_source = CLOUD_APP.read_text()
    normalized_routes = re.sub(r"\{[^}]+\}", "{param}", app_source)
    schema = CLOUD_DB.read_text()
    cloud_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([A-Za-z0-9_]+)\s*\(", schema))
    errors: list[str] = []

    interaction_defaults = config.get("interaction_defaults", {})
    for key in ("trigger", "action", "success", "failure", "preview_behavior", "explain_behavior", "unregistered_behavior"):
        if not interaction_defaults.get(key):
            errors.append(f"interaction_defaults.{key}: is required")

    for feature_id, feature in config["features"].items():
        page = feature["page"]
        if not html.get(page):
            errors.append(f"{feature_id}: page {page} is missing")
        if feature["status"] not in {"implemented", "partial", "prototype", "needs_backend", "missing"}:
            errors.append(f"{feature_id}: unknown status {feature['status']}")
        for table in feature["tables"]:
            if not page.startswith("C"):
                continue
            missing_table_is_expected = feature["status"] == "needs_backend" or config.get("database", {}).get(table, {}).get("status") == "missing"
            if not missing_table_is_expected and not re.search(rf"CREATE TABLE IF NOT EXISTS {re.escape(table)}\s*\(", schema):
                errors.append(f"{feature_id}: table {table} is not in cloud/db.py")
        if page.startswith("C") and feature["status"] != "needs_backend":
            for route in feature["api"]:
                method, path = route.split(" ", 1) if " " in route else (None, route)
                if method and method not in {"GET", "POST", "PUT", "DELETE"}:
                    continue
                if path.startswith("GET/PUT "):
                    continue
                route_fragment = re.sub(r"\{[^}]+\}", "{param}", path.split("?")[0])
                if route_fragment not in normalized_routes:
                    errors.append(f"{feature_id}: route {route} is not in cloud/app.py")

    # database_details may also contain cross-platform design entities that are
    # intentionally not present in the current Cloud prototype schema.
    documented_tables = {
        table for table, detail in config.get("database_details", {}).items()
        if detail.get("validation", "cloud") == "cloud"
    }
    for table in sorted(cloud_tables - documented_tables):
        errors.append(f"database_details: Cloud table {table} is not documented")
    for table in sorted(documented_tables - cloud_tables):
        errors.append(f"database_details: {table} is not present in cloud/db.py")
    for table, detail in config.get("database_details", {}).items():
        if not detail.get("columns") or not detail.get("primary_key"):
            errors.append(f"database_details.{table}: columns and primary_key are required")

    modules = config.get("architecture", {}).get("cloud_control_plane", {}).get("modules", [])
    module_ids = {module.get("id") for module in modules}
    if module_ids != {"auth", "session", "workspace", "device", "model", "audit"}:
        errors.append("architecture.cloud_control_plane: auth/session/workspace/device/model/audit modules are required")
    for module in modules:
        for table in module.get("data", []):
            if table not in cloud_tables:
                errors.append(f"architecture.cloud_control_plane.{module.get('id')}: table {table} is not in cloud/db.py")

    def page_binding_source(page: str) -> str:
        # 绑定选择器可能由页面引用的本地脚本动态渲染，检查范围需包含这些 JS 资产
        parts = [html.get(page, "")]
        page_dir = (DOCS / "pages" / (
            "apps" if page.startswith("APP") else "cloud" if page.startswith(("A", "C"))
            else "desktop" if page.startswith("D") else "mobile"
        ))
        for asset_ref in referenced_assets(parts[0]):
            asset_path = (page_dir / asset_ref).resolve()
            try:
                asset_path.relative_to(DOCS)
            except ValueError:
                continue
            if asset_path.exists():
                parts.append(asset_path.read_text())
        return "\n".join(parts)

    for feature_id, selectors in config.get("bindings", {}).items():
        feature = config["features"].get(feature_id)
        if not feature:
            errors.append(f"binding {feature_id}: feature is missing")
            continue
        source = page_binding_source(feature["page"])
        for selector in selectors:
            token = selector.strip("[]")
            if selector.startswith("."):
                token = selector[1:]
            if token and token not in source:
                errors.append(f"{feature_id}: selector {selector} is not present in {feature['page']}")

    required_page_assets = {
        "C01": "../../assets/c01-live.js",
        "C02": "../../assets/c02-live.js",
        "C03": "../../assets/c03-live.js",
        "C04": "../../assets/c04-live.js",
        "C05": "../../assets/c05-live.js",
        "C06": "../../assets/c06-live.js",
    }
    for page, asset in required_page_assets.items():
        if asset not in referenced_assets(html.get(page, "")):
            errors.append(f"{page}: required live asset {asset} is not loaded")
    for script_name in ("product-docs.js", "page.js"):
        script_source = (DOCS / "assets" / script_name).read_text()
        if "event.target.closest('[data-feature-id]')" not in script_source:
            errors.append(f"{script_name}: explain mode must inherit a feature binding from the nearest container")

    remote = config.get("remote_connection_contract", {})
    if not remote.get("version") or not remote.get("maturity") or not remote.get("invariants"):
        errors.append("remote_connection_contract: version, maturity and invariants are required")
    for section, required_names in {
        "entities": ("CloudConnectionProfile", "RemoteClientBinding", "Device", "Pairing", "Grant", "Remote Session"),
        "flows": ("扫描云端二维码", "扫描远程客户端二维码", "手动添加或编辑", "删除、撤销与恢复"),
        "platforms": ("Cloud Web", "桌面 Host", "移动控制端"),
    }.items():
        names = [item.get("name", "") for item in remote.get(section, [])]
        for name in required_names:
            if not any(item.startswith(name) for item in names):
                errors.append(f"remote_connection_contract.{section}: missing {name}")
    for marker in ("data-remote-summary", "data-remote-entities", "data-remote-flows", "data-remote-states", "data-remote-platforms"):
        if marker not in html.get("A03", ""):
            errors.append(f"A03: missing {marker}")

    a04_source = (DOCS / "assets" / "a04.js").read_text()
    catalog_match = re.search(r"const iconCatalog = '([^']+)'", a04_source)
    catalog = set(catalog_match.group(1).split()) if catalog_match else set()
    mobile_icons = set()
    for page in ("M03", "M08"):
        mobile_icons.update(re.findall(r'data-icon="([^"]+)"', html.get(page, "")))
    mobile_icons.update(re.findall(r"icon\('([^']+)'\)", (DOCS / "assets" / "mobile-remote-settings.js").read_text()))
    for name in sorted(mobile_icons - catalog):
        errors.append(f"A04: icon {name} used by M03/M08 is absent from Iconography")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"validated {len(config['features'])} features, {len(config.get('bindings', {}))} bindings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
