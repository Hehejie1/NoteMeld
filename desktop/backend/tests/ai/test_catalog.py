"""notemeld-ai ModelCapabilities / CapabilityCatalog 单测。

§7.3 capability 报错门禁：
- ModelCapabilities.from_dict 容错处理（None/空 dict/部分字段）
- CapabilityCatalog.get 复用 ModelCapabilityService.get()，只读不探测
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.catalog import CapabilityCatalog, ModelCapabilities  # noqa: E402


class ModelCapabilitiesTest(unittest.TestCase):
    def test_from_dict_none_returns_empty(self):
        caps = ModelCapabilities.from_dict(None)
        self.assertIsNone(caps.supports_json_mode)
        self.assertIsNone(caps.supports_vision)
        self.assertIsNone(caps.supports_tool_calling)
        self.assertIsNone(caps.raw)

    def test_from_dict_empty_returns_empty(self):
        caps = ModelCapabilities.from_dict({})
        self.assertIsNone(caps.supports_json_mode)

    def test_from_dict_full(self):
        data = {
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_tool_calling": True,
        }
        caps = ModelCapabilities.from_dict(data)
        self.assertTrue(caps.supports_json_mode)
        self.assertFalse(caps.supports_vision)
        self.assertTrue(caps.supports_tool_calling)
        self.assertEqual(caps.raw, data)

    def test_from_dict_partial(self):
        """DB 中可能只有部分字段被探测过，其他为 None。"""
        caps = ModelCapabilities.from_dict({"supports_json_mode": True})
        self.assertTrue(caps.supports_json_mode)
        self.assertIsNone(caps.supports_vision)
        self.assertIsNone(caps.supports_tool_calling)


class CapabilityCatalogTest(unittest.TestCase):
    """§7.3：CapabilityCatalog 必须复用 ModelCapabilityService.get()，只读不触发探测。"""

    def test_get_returns_capabilities_from_service(self):
        fake_data = {
            "supports_json_mode": True,
            "supports_vision": False,
            "supports_tool_calling": True,
        }
        with patch("app.ai.catalog.ModelCapabilityService.get", return_value=fake_data) as mocked:
            caps = CapabilityCatalog.get("prov_1", "deepseek-chat")

        mocked.assert_called_once_with("prov_1", "deepseek-chat")
        self.assertTrue(caps.supports_json_mode)
        self.assertFalse(caps.supports_vision)
        self.assertTrue(caps.supports_tool_calling)
        self.assertEqual(caps.raw, fake_data)

    def test_get_returns_empty_when_service_returns_empty(self):
        """ModelCapabilityService.get() 返回 {} 时，所有能力为 None。"""
        with patch("app.ai.catalog.ModelCapabilityService.get", return_value={}):
            caps = CapabilityCatalog.get("prov_1", "unknown-model")
        self.assertIsNone(caps.supports_json_mode)
        self.assertIsNone(caps.supports_vision)
        self.assertIsNone(caps.supports_tool_calling)

    def test_get_does_not_trigger_probe(self):
        """§7.3：CapabilityCatalog 只读，不应调用 ensure_*_capability 触发探测。"""
        with patch("app.ai.catalog.ModelCapabilityService") as MockService:
            MockService.get.return_value = {}
            CapabilityCatalog.get("prov_1", "m")

            # 只允许 get 被调用
            MockService.get.assert_called_once()
            # 不应触发任何 ensure_* 探测方法
            MockService.ensure_json_mode_capability.assert_not_called()
            if hasattr(MockService, "ensure_vision_capability"):
                MockService.ensure_vision_capability.assert_not_called()


if __name__ == "__main__":
    unittest.main()
