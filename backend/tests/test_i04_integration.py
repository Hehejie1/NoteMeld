from pathlib import Path


ROOT = Path(__file__).parents[1]


def read(*parts: str) -> str:
    return (ROOT / Path(*parts)).read_text(encoding="utf-8")


def test_i04_registers_candidate_and_plugin_surfaces_in_one_app_bootstrap():
    app_factory = read("app", "__init__.py")
    init_db = read("app", "db", "init_db.py")
    frontend_app = read("..", "frontend", "src", "App.tsx")
    settings_menu = read("..", "frontend", "src", "pages", "SettingPage", "Menu.tsx")

    assert 'app.include_router(plugins.router, prefix="/api")' in app_factory
    assert 'app.include_router(candidates.router, prefix="/api")' in app_factory
    assert init_db.index("ensure_plugin_migration_registry") < init_db.index("ensure_candidate_migration_registry")
    assert "path=\"plugins\"" in frontend_app
    assert "path=\"candidates\"" in frontend_app
    assert "path: '/settings/plugins'" in settings_menu
    assert "path: '/settings/candidates'" in settings_menu


def test_i04_candidate_plugin_scope_requires_installed_plugin_and_n03_handoff():
    candidate_service = read("app", "services", "candidates", "service.py")

    assert "PluginInstallation" in candidate_service
    assert "plugin scope must target an installed plugin" in candidate_service
    assert "convert to an N03 standard package" in candidate_service
    assert "active-pointer" in candidate_service
    assert "activated" not in candidate_service


def test_i04_external_entrypoints_use_agent_host_boundaries():
    mcp_service = read("app", "mcp", "service.py")
    cli = read("..", "scripts", "notemeld-agent.py")

    assert "NoteMeldToolDriver" in mcp_service
    assert '"/capabilities/note:create"' not in mcp_service
    assert 'request("POST", "/capabilities/note:create"' in cli
    assert "/chat/free" not in cli
    assert "/chat/ask" not in cli
    assert "sqlite" not in cli.lower()
    assert "AgentEvent" not in cli
