"""notemeld-ai 标准化异常分类单测。

覆盖 §7.4 Auth/Network/RateLimit/Capability 类型化错误。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.errors import (  # noqa: E402
    ProviderAuthError,
    ProviderCapabilityError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
)


class ProviderErrorTest(unittest.TestCase):
    def test_base_error_carries_provider_and_model(self):
        err = ProviderError("boom", provider_id="prov_1", model_name="deepseek-chat")
        self.assertEqual(str(err), "boom")
        self.assertEqual(err.provider_id, "prov_1")
        self.assertEqual(err.model_name, "deepseek-chat")

    def test_base_error_defaults_to_none(self):
        err = ProviderError("boom")
        self.assertIsNone(err.provider_id)
        self.assertIsNone(err.model_name)

    def test_all_specific_errors_are_subclasses_of_provider_error(self):
        for cls in (
            ProviderAuthError,
            ProviderNetworkError,
            ProviderRateLimitError,
            ProviderCapabilityError,
        ):
            self.assertTrue(issubclass(cls, ProviderError), cls.__name__)

    def test_auth_error_inherits_fields(self):
        err = ProviderAuthError("401", provider_id="p", model_name="m")
        self.assertIsInstance(err, ProviderError)
        self.assertEqual(err.provider_id, "p")
        self.assertEqual(err.model_name, "m")

    def test_network_error_attaches_cause(self):
        original = ConnectionError("reset")
        err = ProviderNetworkError(
            "timeout",
            provider_id="p",
            model_name="m",
            cause=original,
        )
        self.assertIs(err.__cause__, original)

    def test_rate_limit_error_carries_fields(self):
        err = ProviderRateLimitError("429", provider_id="p", model_name="m")
        self.assertEqual(err.provider_id, "p")

    def test_capability_error_exposes_capability_field(self):
        err = ProviderCapabilityError(
            "no tools",
            provider_id="p",
            model_name="m",
            capability="tool_calling",
        )
        self.assertEqual(err.capability, "tool_calling")
        # 未指定时为 None
        err2 = ProviderCapabilityError("no tools")
        self.assertIsNone(err2.capability)


if __name__ == "__main__":
    unittest.main()
