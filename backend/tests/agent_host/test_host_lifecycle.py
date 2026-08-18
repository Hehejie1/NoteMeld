from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_fastapi_lifespan_starts_shared_host_and_cleans_descriptor(monkeypatch, tmp_path):
    import main
    from app.core.agent_runtime_descriptor import descriptor_path, read_descriptor

    fake_host = SimpleNamespace(
        _loaded=SimpleNamespace(sdk_version="0.1.0"),
        started=False,
    )

    def start():
        fake_host.started = True

    fake_host.start = start
    closed: list[bool] = []
    monkeypatch.setattr(main, "get_agent_sdk_host", lambda: fake_host)
    monkeypatch.setattr(main, "close_agent_sdk_host", lambda: closed.append(True))
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main.agent_store, "recover_nonterminal", lambda: [])
    monkeypatch.setattr(main, "register_handler", lambda: None)
    monkeypatch.setattr(main, "run_startup_template_task_cleanup", lambda: 0)
    monkeypatch.setattr(main.TranscriberConfigManager, "get_config", lambda _self: {"transcriber_type": "none", "whisper_model_size": "tiny"})
    monkeypatch.setenv("NOTEMELD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_PORT", "9999")

    async def exercise():
        async with main.lifespan(SimpleNamespace()):
            assert fake_host.started is True
            descriptor = read_descriptor(tmp_path)
            assert descriptor is not None
            assert descriptor.pid > 0
            assert descriptor.abi_version == 2
            assert descriptor.base_url.endswith(":9999/api")
            assert descriptor_path(tmp_path).exists()
        assert closed == [True]
        assert not descriptor_path(tmp_path).exists()

    asyncio.run(exercise())
