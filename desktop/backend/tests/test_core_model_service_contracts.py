import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[3]


class TestCoreModelServiceContracts(unittest.TestCase):
    def test_add_new_model_does_not_probe_capability_on_save(self):
        model_service = (ROOT / "desktop" / "backend" / "app" / "services" / "model.py").read_text(encoding="utf-8")

        add_new_model_section = model_service.split("def add_new_model", 1)[1]
        add_new_model_section = add_new_model_section.split("if __name__ == '__main__':", 1)[0]

        self.assertNotIn("probe_json_mode_safe", add_new_model_section)

    def test_add_new_model_requires_and_persists_explicit_runtime_configuration(self):
        from app.services.model import ModelService

        saved_model = {
            "id": 7,
            "provider_id": "provider-1",
            "model_name": "runtime-model",
            "context_window_tokens": 131072,
            "supports_vision": True,
            "supports_stream": False,
            "created_at": None,
        }
        with patch("app.services.model.ProviderService.get_provider_by_id", return_value={"id": "provider-1"}), patch(
            "app.services.model.get_model_by_provider_and_name", return_value=None
        ), patch("app.services.model.insert_model", return_value=saved_model) as insert_model:
            result = ModelService.add_new_model(
                "provider-1",
                "runtime-model",
                131072,
                True,
                False,
            )

        self.assertEqual(result, saved_model)
        insert_model.assert_called_once_with(
            provider_id="provider-1",
            model_name="runtime-model",
            context_window_tokens=131072,
            supports_vision=True,
            supports_stream=False,
        )

    def test_build_saved_model_config_uses_complete_persisted_runtime_row(self):
        from app.services.model import ModelService

        provider = {
            "id": "provider-1",
            "name": "Provider",
            "api_key": "sk-test",
            "base_url": "https://example.invalid/v1",
        }
        saved_model = {
            "id": 7,
            "provider_id": "provider-1",
            "model_name": "runtime-model",
            "context_window_tokens": 131072,
            "supports_vision": True,
            "supports_stream": False,
            "created_at": None,
        }

        with patch.object(ModelService, "get_saved_model", return_value=saved_model):
            config = ModelService.build_saved_model_config(
                provider,
                "runtime-model",
                usage_context={"phase": "research"},
            )

        self.assertEqual(config.context_window_tokens, 131072)
        self.assertIs(config.supports_vision, True)
        self.assertIs(config.supports_stream, False)
        self.assertEqual(config.usage_context, {"phase": "research"})


if __name__ == "__main__":
    unittest.main()
