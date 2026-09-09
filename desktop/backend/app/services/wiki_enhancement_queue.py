from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from app.services.wiki_job_store import WikiJobStore
from app.services.wiki_pipeline import WikiPipeline
from app.services.wiki_rebuild_service import request_wiki_rebuild
from app.utils.logger import get_logger


logger = get_logger(__name__)


def schedule_wiki_extraction(
    output_dir: Path,
    task_id: str,
    summary_input,
    markdown: str,
    gpt,
    update_status: Callable[[str, str], None] | None = None,
) -> None:
    delay = float(os.getenv("WIKI_EXTRACTION_DELAY_SECONDS", "0"))

    def _run() -> None:
        job_store = WikiJobStore(output_dir=output_dir)
        try:
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            job_store.write(task_id, "running", stage="analysis", detail="后台提取 Wiki 知识", recoverable=True)
            payload = WikiPipeline(output_dir=output_dir).extract_contribution(
                summary_input,
                markdown,
                gpt=gpt,
            )
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            status = payload.get("status", "success")
            job_store.write(
                task_id,
                status,
                stage="analysis",
                error=payload.get("analysis_error", ""),
                reason=payload.get("reason", ""),
                detail=payload.get("detail", ""),
                recoverable=payload.get("recoverable", False),
            )
            if update_status:
                update_status(task_id, status)
            request_wiki_rebuild(output_dir, gpt=gpt, reason=f"task:{task_id}:analysis_complete")
            if status == "partial":
                schedule_partial_wiki_enhancement(output_dir, task_id, summary_input, markdown, gpt, update_status)
        except Exception as exc:
            logger.error("Wiki extraction failed for task %s: %s", task_id, exc)
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            job_store.write(
                task_id,
                "failed",
                stage=getattr(exc, "stage", "analysis"),
                error=str(exc),
                reason="analysis_error",
                detail=str(exc),
                recoverable=True,
            )
            if update_status:
                update_status(task_id, "failed")

    timer = threading.Timer(delay, _run)
    timer.daemon = True
    timer.start()


def schedule_partial_wiki_enhancement(
    output_dir: Path,
    task_id: str,
    summary_input,
    markdown: str,
    gpt,
    update_status: Callable[[str, str], None] | None = None,
) -> None:
    delay = float(os.getenv("WIKI_PARTIAL_ENHANCE_DELAY_SECONDS", "10"))

    def _run() -> None:
        job_store = WikiJobStore(output_dir=output_dir)
        try:
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            job_store.write(task_id, "running", stage="enhance", reason="partial_enhancement", detail="后台增强基础 Wiki", recoverable=True)
            payload = WikiPipeline(output_dir=output_dir).extract_contribution(
                summary_input,
                markdown,
                gpt=gpt,
                source_only_on_failure=False,
            )
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            status = payload.get("status", "success")
            job_store.write(task_id, status, stage="analysis")
            if update_status:
                update_status(task_id, status)
            request_wiki_rebuild(output_dir, gpt=gpt, reason=f"task:{task_id}:enhanced")
        except Exception as exc:
            logger.warning("Partial Wiki enhancement failed: task_id=%s error=%s", task_id, exc)
            if job_store.read(task_id).get("status") == "canceled":
                if update_status:
                    update_status(task_id, "canceled")
                return
            job_store.write(
                task_id,
                "partial",
                stage=getattr(exc, "stage", "enhance"),
                error=str(exc),
                reason="partial_enhancement_failed",
                detail=str(exc),
                recoverable=True,
            )
            if update_status:
                update_status(task_id, "partial")

    timer = threading.Timer(delay, _run)
    timer.daemon = True
    timer.start()
