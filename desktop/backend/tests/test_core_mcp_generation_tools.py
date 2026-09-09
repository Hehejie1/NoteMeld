import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp.service import McpToolService  # noqa: E402
from app.routers.mcp import _tool_call_result  # noqa: E402


class FakeGenerationClient:
    def __init__(self, statuses=None, note=None):
        self.submitted_payloads = []
        self.statuses = list(statuses or [])
        self.note = note or {"taskId": "task-1", "markdown": "# Saved note"}

    def submit_note(self, payload):
        self.submitted_payloads.append(payload)
        return {"taskId": "task-1", "message": "queued"}

    def get_task(self, task_id):
        if self.statuses:
            return self.statuses.pop(0)
        return {"taskId": task_id, "status": "PENDING", "message": "still running"}

    def read_note(self, task_id):
        return {**self.note, "taskId": task_id}


class McpGenerationToolsTest(unittest.TestCase):
    def test_lists_bilinote_style_generation_tools(self):
        service = McpToolService(generation_client=FakeGenerationClient())

        tool_names = {tool["name"] for tool in service.list_tools()}

        self.assertIn("generate_note", tool_names)
        self.assertIn("get_task", tool_names)
        self.assertIn("get_note", tool_names)
        self.assertIn("list_models", tool_names)

    def test_generate_note_waits_and_returns_markdown_when_task_succeeds(self):
        client = FakeGenerationClient(
            statuses=[
                {"taskId": "task-1", "status": "PENDING", "message": "queued"},
                {"taskId": "task-1", "status": "SUCCESS", "result": {"markdown": "# Generated note"}},
            ]
        )
        service = McpToolService(generation_client=client)

        result = service.call_tool(
            "generate_note",
            {
                "url": "https://www.douyin.com/video/123",
                "model": "GPT-5.5",
                "providerId": "provider-1",
                "maxWaitSeconds": 1,
                "pollIntervalSeconds": 0,
            },
        )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["taskId"], "task-1")
        self.assertEqual(result["markdown"], "# Generated note")
        self.assertEqual(client.submitted_payloads[0]["video_url"], "https://www.douyin.com/video/123")
        self.assertEqual(client.submitted_payloads[0]["model_name"], "GPT-5.5")
        self.assertEqual(client.submitted_payloads[0]["provider_id"], "provider-1")

    def test_generate_note_selects_default_model_when_only_url_is_provided(self):
        client = FakeGenerationClient(
            statuses=[
                {"taskId": "task-1", "status": "SUCCESS", "result": {"markdown": "# Generated note"}},
            ]
        )
        service = McpToolService(
            generation_client=client,
            model_catalog=lambda: [
                {
                    "providerId": "freemodel",
                    "providerName": "Free Model",
                    "model": "gpt-5.5",
                }
            ],
        )

        result = service.call_tool(
            "generate_note",
            {
                "url": "https://www.douyin.com/video/123",
                "maxWaitSeconds": 1,
                "pollIntervalSeconds": 0,
            },
        )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(client.submitted_payloads[0]["model_name"], "gpt-5.5")
        self.assertEqual(client.submitted_payloads[0]["provider_id"], "freemodel")
        self.assertEqual(client.submitted_payloads[0]["style"], "")
        self.assertFalse(client.submitted_payloads[0]["screenshot"])

    def test_generate_note_returns_task_id_when_wait_times_out(self):
        client = FakeGenerationClient(
            statuses=[
                {"taskId": "task-1", "status": "TRANSCRIBING", "message": "transcribing"},
            ]
        )
        service = McpToolService(generation_client=client)

        result = service.call_tool(
            "generate_note",
            {
                "url": "https://www.douyin.com/video/123",
                "model": "GPT-5.5",
                "providerId": "provider-1",
                "maxWaitSeconds": 0,
                "pollIntervalSeconds": 0,
            },
        )

        self.assertEqual(result["status"], "TRANSCRIBING")
        self.assertEqual(result["taskId"], "task-1")
        self.assertIn("get_task", result["next"])
        self.assertNotIn("markdown", result)

    def test_get_note_reads_markdown_by_task_id(self):
        service = McpToolService(
            generation_client=FakeGenerationClient(note={"taskId": "task-1", "markdown": "# Existing note"})
        )

        result = service.call_tool("get_note", {"taskId": "task-1"})

        self.assertEqual(result["taskId"], "task-1")
        self.assertEqual(result["markdown"], "# Existing note")

    def test_list_models_returns_enabled_models_without_api_keys(self):
        service = McpToolService(
            generation_client=FakeGenerationClient(),
            model_catalog=lambda: [
                {
                    "providerId": "provider-1",
                    "providerName": "coco",
                    "model": "GPT-5.5",
                    "baseUrl": "http://127.0.0.1:8000/v1",
                }
            ],
        )

        result = service.call_tool("list_models", {})

        self.assertEqual(result["models"][0]["providerId"], "provider-1")
        self.assertEqual(result["models"][0]["model"], "GPT-5.5")
        self.assertNotIn("apiKey", result["models"][0])
        self.assertNotIn("api_key", result["models"][0])

    def test_tool_call_result_uses_markdown_as_display_text(self):
        result = _tool_call_result({"taskId": "task-1", "status": "SUCCESS", "markdown": "# Note"})

        self.assertEqual(result["content"][0]["text"], "# Note")
        self.assertEqual(result["structuredContent"]["taskId"], "task-1")

    def test_default_generation_client_reads_note_markdown_from_task_file(self):
        from app.mcp.service import LocalNoteGenerationClient

        with tempfile.TemporaryDirectory() as tmp_dir:
            task_path = pathlib.Path(tmp_dir) / "task-1.json"
            task_path.write_text('{"markdown":"# File note"}', encoding="utf-8")
            client = LocalNoteGenerationClient(api_base_url="http://127.0.0.1:8483/api", output_dir=pathlib.Path(tmp_dir))

            result = client.read_note("task-1")

        self.assertEqual(result["taskId"], "task-1")
        self.assertEqual(result["markdown"], "# File note")

    def test_default_generation_client_adds_conversation_id_before_submit(self):
        from app.mcp.service import LocalNoteGenerationClient

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"code": 0, "msg": "success", "data": {"task_id": "task-1"}}

        class FakeHttpClient:
            def __init__(self):
                self.posts = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, json):
                self.posts.append((url, json))
                return FakeResponse()

        fake_http_client = FakeHttpClient()
        client = LocalNoteGenerationClient(
            api_base_url="http://127.0.0.1:8483/api",
            http_client_factory=lambda timeout: fake_http_client,
            conversation_preparer=lambda payload: "conversation-1",
        )

        result = client.submit_note(
            {
                "video_url": "https://www.douyin.com/video/123",
                "platform": "douyin",
                "quality": "medium",
                "model_name": "gpt-5.5",
                "provider_id": "freemodel",
            }
        )

        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(fake_http_client.posts[0][1]["conversation_id"], "conversation-1")

    def test_get_note_rejects_path_traversal_task_id(self):
        from app.mcp.service import LocalNoteGenerationClient

        with tempfile.TemporaryDirectory() as tmp_dir:
            client = LocalNoteGenerationClient(api_base_url="http://127.0.0.1:8483/api", output_dir=pathlib.Path(tmp_dir))

            with self.assertRaises(ValueError):
                client.read_note("../not-allowed")


if __name__ == "__main__":
    unittest.main()
