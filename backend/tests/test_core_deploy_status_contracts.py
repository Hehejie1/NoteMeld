import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


class TestCoreDeployStatusContracts(unittest.TestCase):
    def test_mcp_status_reports_fixed_desktop_url_and_tool_count(self):
        from app.routers import config

        with patch.dict("os.environ", {"BACKEND_PORT": "8483"}, clear=False):
            with patch.object(config.McpToolService, "list_tools", return_value=[{"name": "a"}, {"name": "b"}]):
                status = config._mcp_status()

        self.assertEqual(status["status"], "running")
        self.assertEqual(status["url"], "http://127.0.0.1:8483/mcp")
        self.assertEqual(status["port"], 8483)
        self.assertEqual(status["tools_count"], 2)
        self.assertFalse(status["auth_required"])
        self.assertIsNone(status["error"])

    def test_mcp_status_reports_error_without_crashing_deploy_status(self):
        from app.routers import config

        with patch.dict("os.environ", {"BACKEND_PORT": "8483"}, clear=False):
            with patch.object(config.McpToolService, "list_tools", side_effect=RuntimeError("boom")):
                status = config._mcp_status()

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["url"], "http://127.0.0.1:8483/mcp")
        self.assertEqual(status["tools_count"], 0)
        self.assertIn("boom", status["error"])


if __name__ == "__main__":
    unittest.main()
