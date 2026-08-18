from __future__ import annotations

import asyncio

from app.agent_host.drivers.tools import NoteMeldToolDriver


class FakeTool:
    name = "search_knowledge"
    description = "search"
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}}
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
        assert result["call_id"] == "c1"
        assert progress[0]["progress"] == 0.5
    asyncio.run(exercise())


def test_tool_driver_rejects_unknown_tool():
    async def exercise():
        driver = NoteMeldToolDriver(FakeRegistry())
        try:
            await driver.invoke({"call_id": "c1", "tool_name": "missing", "arguments": {}}, {}, lambda _: None)
        except ValueError as error:
            assert "tool" in str(error)
        else:
            raise AssertionError("unknown tool should fail")
    asyncio.run(exercise())
