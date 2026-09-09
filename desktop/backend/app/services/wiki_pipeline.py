import json
import logging
from dataclasses import asdict
from pathlib import Path

from app.renderers.export_outline_renderer import ExportOutlineRenderer
from app.services.knowledge_extractor import KnowledgeExtractor
from app.services.wiki_store import WikiStore


logger = logging.getLogger(__name__)


class WikiPipelineStageError(RuntimeError):
    def __init__(self, stage: str, original: Exception):
        super().__init__(str(original))
        self.stage = stage
        self.original = original


def classify_wiki_error(exc: Exception) -> dict:
    message = str(exc)
    lower = message.lower()
    if "504" in message or "timeout" in lower or "timed out" in lower:
        reason = "timeout"
    elif "json" in lower:
        reason = "json_parse_error"
    elif "response_format" in lower or "not supported" in lower:
        reason = "capability_unsupported"
    else:
        reason = "analysis_error"
    return {"reason": reason, "detail": message, "recoverable": True}


class WikiPipeline:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, file_name: str, payload: dict) -> Path:
        path = self.output_dir / file_name
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return path

    def run(self, summary_input, markdown: str, gpt=None):
        extractor = KnowledgeExtractor()
        analysis = extractor.analyze(summary_input, markdown, gpt=gpt)
        self._write_json(f"{summary_input.input_id}_knowledge_analysis.json", asdict(analysis))
        packet = extractor.build_packet(analysis)
        return packet

    def analyze(self, summary_input, markdown: str, gpt=None):
        analysis = KnowledgeExtractor().analyze(summary_input, markdown, gpt=gpt)
        self._write_json(f"{summary_input.input_id}_knowledge_analysis.json", asdict(analysis))
        return analysis

    def extract_contribution(self, summary_input, markdown: str, gpt=None, source_only_on_failure: bool = True) -> dict:
        extractor = KnowledgeExtractor()
        status = "success"
        analysis_error = ""
        error_info = {"reason": "", "detail": "", "recoverable": False}
        try:
            analysis = self.analyze(summary_input, markdown, gpt=gpt)
        except Exception as exc:
            if not source_only_on_failure:
                raise WikiPipelineStageError("analysis", exc) from exc
            error_info = classify_wiki_error(exc)
            status = "partial"
            analysis_error = str(exc)
            analysis = extractor.build_source_only_analysis(summary_input, markdown)
            self._write_json(f"{summary_input.input_id}_knowledge_analysis.json", asdict(analysis))

        packet = extractor.build_packet(analysis)
        if summary_input.user_options.get("output_type") == "export_outline":
            self._write_json(
                f"{summary_input.input_id}_export_outline.json",
                ExportOutlineRenderer().render(summary_input, packet),
            )
        paths = WikiStore(base_dir=self.output_dir / "wiki").persist_contribution(packet, markdown)
        try:
            from app.services.knowledge_article_service import KnowledgeArticleService

            KnowledgeArticleService().index_from_packet(packet, markdown)
        except Exception as exc:  # noqa: BLE001 - Note/Wiki success must not depend on indexing
            # The contribution is already durable; the next reindex job can
            # rebuild K0-K3 without making the Note look failed.
            logger.warning("K0-K3 index failed after Wiki contribution: article_id=%s error=%s", packet.source_id, exc)
        return {
            "analysis": analysis,
            "packet": packet,
            "paths": paths,
            "status": status,
            "analysis_error": analysis_error,
            "reason": "source_only_partial" if status == "partial" else error_info["reason"],
            "detail": error_info["detail"],
            "recoverable": error_info["recoverable"],
        }

    def execute(self, summary_input, markdown: str, gpt=None, stage_callback=None, source_only_on_failure: bool = True) -> dict:
        extractor = KnowledgeExtractor()
        status = "success"
        analysis_error = ""
        if stage_callback is not None:
            stage_callback("analysis")
        try:
            analysis = self.analyze(summary_input, markdown, gpt=gpt)
        except Exception as exc:
            if not source_only_on_failure:
                raise WikiPipelineStageError("analysis", exc) from exc
            error_info = classify_wiki_error(exc)
            status = "partial"
            analysis_error = str(exc)
            analysis = extractor.build_source_only_analysis(summary_input, markdown)
            self._write_json(f"{summary_input.input_id}_knowledge_analysis.json", asdict(analysis))
        packet = extractor.build_packet(analysis)
        if summary_input.user_options.get("output_type") == "export_outline":
            self._write_json(
                f"{summary_input.input_id}_export_outline.json",
                ExportOutlineRenderer().render(summary_input, packet),
            )
        if stage_callback is not None:
            stage_callback("materialize")
        try:
            paths = WikiStore(base_dir=self.output_dir / "wiki").persist(packet, markdown, gpt=gpt)
        except Exception as exc:
            raise WikiPipelineStageError("materialize", exc) from exc
        if status == "partial":
            return {
                "analysis": analysis,
                "packet": packet,
                "paths": paths,
                "status": status,
                "analysis_error": analysis_error,
                "reason": "source_only_partial",
                "detail": error_info["detail"],
                "recoverable": True,
            }
        return {"analysis": analysis, "packet": packet, "paths": paths, "status": status, "analysis_error": analysis_error, "reason": "", "detail": "", "recoverable": False}

    def materialize(self, summary_input, markdown: str, gpt=None) -> dict:
        return self.execute(summary_input, markdown, gpt=gpt)
