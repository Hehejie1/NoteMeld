from __future__ import annotations

import asyncio

from app.agent_host.drivers.tools import NoteMeldToolDriver


class FakeTool:
    name = "search_knowledge"
    description = "search"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
    }
    execution_mode = "serial"

    async def execute(self, call_id, params, signal, on_update):
        await on_update({"message": "working", "progress": 0.5})
        return {"call_id": call_id, "content": [{"type": "text", "text": params["query"]}]}


class FakeRegistry:
    async def describe(self, names):
        return [{"id": "local:search_knowledge", "name": "search_knowledge"}]

    def get_tool(self, name):
        return FakeTool() if name == "search_knowledge" else None

    async def invoke(self, name, arguments, call_id, signal, on_update):
        return await self.get_tool(name).execute(call_id, arguments, signal, on_update)


def test_tool_driver_registers_describes_and_invokes_tools():
    async def exercise():
        progress = []
        driver = NoteMeldToolDriver(FakeRegistry())

        descriptors = await driver.describe(["search_knowledge"])
        result = await driver.invoke(
            {"call_id": "c1", "tool_name": "search_knowledge", "arguments": {"query": "x"}},
            {"session_id": "s1", "turn_id": "t1"},
            progress.append,
        )

        assert descriptors[0]["name"] == "search_knowledge"
        assert result == {
            "call_id": "c1",
            "output": {
                "ok": True,
                "result": {"call_id": "c1", "content": [{"type": "text", "text": "x"}]},
            },
        }
        assert progress[0]["progress"] == 0.5
    asyncio.run(exercise())


def test_tool_driver_rejects_unknown_tool():
    async def exercise():
        driver = NoteMeldToolDriver(FakeRegistry())
        result = await driver.invoke(
            {"call_id": "c1", "tool_name": "missing", "arguments": {}},
            {},
            lambda _: None,
        )
        assert result["output"] == {
            "ok": False,
            "error": {"code": "unknown_tool", "message": "工具不存在或未授权"},
        }
    asyncio.run(exercise())


def test_tool_driver_classifies_invalid_arguments_before_product_execution():
    async def exercise():
        driver = NoteMeldToolDriver(FakeRegistry())
        result = await driver.invoke(
            {"call_id": "c1", "tool_name": "search_knowledge", "arguments": {}},
            {},
        )
        assert result["output"]["error"]["code"] == "invalid_arguments"

        result = await driver.invoke(
            {"call_id": "c2", "tool_name": "search_knowledge", "arguments": []},
            {},
        )
        assert result["output"]["error"]["code"] == "invalid_arguments"
    asyncio.run(exercise())


def test_tool_driver_classifies_product_failures_without_leaking_details():
    class BusinessError(Exception):
        code = "business_error"

    class FailingRegistry(FakeRegistry):
        error = RuntimeError("SENSITIVE_PROVIDER_PAYLOAD")

        async def invoke(self, name, arguments, call_id, signal, on_update):
            raise self.error

    async def exercise():
        registry = FailingRegistry()
        driver = NoteMeldToolDriver(registry)
        cases = [
            (PermissionError("SENSITIVE_PERMISSION_DETAIL"), "permission_denied"),
            (BusinessError("SENSITIVE_BUSINESS_DETAIL"), "business_error"),
            (RuntimeError("SENSITIVE_PROVIDER_PAYLOAD"), "tool_execution_error"),
        ]
        for index, (error, expected) in enumerate(cases):
            registry.error = error
            result = await driver.invoke(
                {
                    "call_id": f"c{index}",
                    "tool_name": "search_knowledge",
                    "arguments": {"query": "SENSITIVE_ARGUMENT"},
                },
                {},
            )
            serialized = str(result)
            assert result["output"]["error"]["code"] == expected
            assert "SENSITIVE" not in serialized
    asyncio.run(exercise())


def test_tool_driver_accepts_synchronous_registry_describe():
    class SyncRegistry(FakeRegistry):
        def describe(self, names):
            return [{"name": name} for name in names]

    descriptors = asyncio.run(NoteMeldToolDriver(SyncRegistry()).describe(["search_knowledge"]))
    assert descriptors == [{"name": "search_knowledge"}]
