from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.ai.errors import ProviderCapabilityError
from app.gpt.notemeld_gpt import NotemeldGPT
from app.models.learning_canvas import LearningSource
from app.routers import note as note_router
from app.services.note_style_image_vlm_analyzer import analyze_image_with_vlm
from app.services.research_note_compiler import build_llm_research_compiler
from app.services.web_note import WebNoteGenerator


PROVIDER_ID = "provider-runtime"
MODEL_NAME = "runtime-model"
PROVIDER_ROW = {
    "id": PROVIDER_ID,
    "name": "Runtime Provider",
    "api_key": "sk-test",
    "base_url": "https://example.invalid/v1",
}
SAVED_MODEL_ROW = {
    "id": 7,
    "provider_id": PROVIDER_ID,
    "model_name": MODEL_NAME,
    "context_window_tokens": 131072,
    "supports_vision": False,
    "supports_stream": False,
}


def _fake_from_config(config):
    return NotemeldGPT(
        client=MagicMock(),
        model=config.model_name,
        provider_id=config.provider,
        provider_name=config.name,
        base_url=config.base_url,
        usage_context=config.usage_context,
        context_window_tokens=config.context_window_tokens,
        supports_vision=config.supports_vision,
        supports_stream=config.supports_stream,
    )


def test_saved_vision_false_rejects_image_even_when_probe_is_true(tmp_path):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"not-a-real-image-but-data-url-safe")

    with patch(
        "app.db.model_capability_dao.get_model_capability",
        return_value={"supports_vision": True},
    ), patch(
        "app.services.note.ProviderService.get_provider_by_id",
        return_value=PROVIDER_ROW,
    ), patch(
        "app.services.note.ModelService.get_saved_model",
        return_value=SAVED_MODEL_ROW,
    ), patch(
        "app.services.note.NotemeldGPT.from_config",
        side_effect=_fake_from_config,
    ), patch("app.gpt.notemeld_gpt.create_models") as create_models:
        with pytest.raises(ProviderCapabilityError) as error:
            analyze_image_with_vlm(
                file_path=str(image_path),
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            )

    assert error.value.capability == "vision"
    assert error.value.provider_id == PROVIDER_ID
    assert error.value.model_name == MODEL_NAME
    create_models.assert_not_called()


def test_probe_vision_false_does_not_override_saved_vision_true(tmp_path):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"image")
    saved_vision_model = {**SAVED_MODEL_ROW, "supports_vision": True}
    fake_gpt = MagicMock()
    fake_gpt.create_chat_completion.return_value = SimpleNamespace()
    fake_gpt._extract_message_content.return_value = json.dumps(
        {
            "doc_type": "note",
            "layout": {
                "columns": 1,
                "layout_type": "single-column",
                "reading_order": "top-to-bottom",
            },
            "blocks": [{"id": "b1", "block_type": "paragraph", "text": "ok"}],
        }
    )

    with patch(
        "app.db.model_capability_dao.get_model_capability",
        return_value={"supports_vision": False},
    ), patch(
        "app.services.note.ProviderService.get_provider_by_id",
        return_value=PROVIDER_ROW,
    ), patch(
        "app.services.note.ModelService.get_saved_model",
        return_value=saved_vision_model,
    ), patch(
        "app.services.note.NotemeldGPT.from_config",
        return_value=fake_gpt,
    ), patch(
        "app.services.note_style_image_vlm_analyzer._normalize_structure_payload",
        side_effect=lambda payload: payload,
    ):
        result = analyze_image_with_vlm(
            file_path=str(image_path),
            provider_id=PROVIDER_ID,
            model_name=MODEL_NAME,
        )

    assert result["doc_type"] == "note"
    fake_gpt.create_chat_completion.assert_called_once()


def test_notemeld_gpt_uses_config_provider_identity_without_usage_context():
    model = MagicMock()
    models = MagicMock()
    models.get_model.return_value = model
    models.complete = MagicMock()

    async def complete(*args, **kwargs):
        from app.ai.stream import CompleteResult

        return CompleteResult(content="ok")

    models.complete.side_effect = complete
    gpt = NotemeldGPT(
        client=MagicMock(),
        model=MODEL_NAME,
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_ROW["name"],
        base_url=PROVIDER_ROW["base_url"],
    )

    with patch("app.gpt.notemeld_gpt.create_models", return_value=models):
        gpt.create_chat_completion(messages=[{"role": "user", "content": "hello"}])

    models.get_model.assert_called_once_with(PROVIDER_ID, MODEL_NAME)


def test_web_note_uses_saved_runtime_config():
    with patch(
        "app.services.provider.ProviderService.get_provider_by_id",
        return_value=PROVIDER_ROW,
    ), patch(
        "app.services.model.ModelService.get_saved_model",
        return_value=SAVED_MODEL_ROW,
    ), patch(
        "app.gpt.notemeld_gpt.OpenAICompatibleProvider"
    ) as provider_cls:
        provider_cls.return_value.get_client = MagicMock()
        gpt = WebNoteGenerator.__new__(WebNoteGenerator)._get_gpt(MODEL_NAME, PROVIDER_ID)

    assert gpt.context_window_tokens == 131072
    assert gpt.supports_vision is False
    assert gpt.supports_stream is False


def test_research_compiler_uses_saved_runtime_config():
    captured = []
    fake_gpt = MagicMock()
    fake_gpt.create_chat_completion.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"status":"clarifying"}'))]
    )
    fake_gpt._extract_message_content.return_value = '{"status":"clarifying"}'

    def capture_config(config):
        captured.append(config)
        return fake_gpt

    with patch(
        "app.services.provider.ProviderService.get_provider_by_id",
        return_value=PROVIDER_ROW,
    ), patch(
        "app.services.model.ModelService.get_saved_model",
        return_value=SAVED_MODEL_ROW,
    ), patch(
        "app.gpt.notemeld_gpt.NotemeldGPT.from_config",
        side_effect=capture_config,
    ):
        build_llm_research_compiler()(
            goal="runtime config",
            local_nodes=[],
            sources=[
                LearningSource(
                    id="source-1",
                    source_type="web",
                    provider="test",
                    title="Source",
                )
            ],
            provider_id=PROVIDER_ID,
            model_name=MODEL_NAME,
        )

    config = captured[0]
    assert config.context_window_tokens == 131072
    assert config.supports_vision is False
    assert config.supports_stream is False


def test_wiki_retry_uses_saved_runtime_config(tmp_path, monkeypatch):
    task_id = "retry-runtime"
    summary_input = {
        "input_id": task_id,
        "input_type": "web",
        "source_url": "https://example.test",
        "platform": "web_link",
        "title": "Retry",
        "user_goal": None,
        "user_options": {
            "provider_id": PROVIDER_ID,
            "model_name": MODEL_NAME,
            "output_type": "note_markdown",
        },
        "page_context": None,
        "transcript_context": None,
        "vision_context": None,
        "social_context": None,
        "meta_context": {
            "resource_type": "web",
            "provider_id": PROVIDER_ID,
            "model_name": MODEL_NAME,
        },
        "document_context": None,
    }
    (tmp_path / f"{task_id}_summary_input.json").write_text(
        json.dumps(summary_input), encoding="utf-8"
    )
    (tmp_path / f"{task_id}.json").write_text(
        json.dumps({"markdown": "# Note"}), encoding="utf-8"
    )
    monkeypatch.setattr(note_router, "NOTE_OUTPUT_DIR", str(tmp_path))

    captured = []
    fake_gpt = MagicMock()

    def capture_config(config):
        captured.append(config)
        return fake_gpt

    pipeline = MagicMock()
    pipeline.extract_contribution.return_value = {"status": "success"}
    background_tasks = BackgroundTasks()
    with patch(
        "app.services.provider.ProviderService.get_provider_by_id",
        return_value=PROVIDER_ROW,
    ), patch(
        "app.services.model.ModelService.get_saved_model",
        return_value=SAVED_MODEL_ROW,
    ), patch(
        "app.gpt.notemeld_gpt.NotemeldGPT.from_config",
        side_effect=capture_config,
    ), patch(
        "app.services.wiki_pipeline.WikiPipeline",
        return_value=pipeline,
    ), patch("app.services.wiki_rebuild_service.request_wiki_rebuild"):
        note_router.retry_wiki_extraction(task_id, background_tasks)
        asyncio.run(background_tasks())

    config = captured[0]
    assert config.context_window_tokens == 131072
    assert config.supports_vision is False
    assert config.supports_stream is False
