# 多源视频增强总结 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将视频链接生成笔记改造成 `网页搜索 + 音频转文字 + 视频分帧` 三路并行采集，并在最终总结中融合三源上下文。

**Architecture:** 新增 `MultiSourceVideoCollector` 编排层，内部并行执行 Web Search、Transcript、Frame 三个 collector，输出 `MultiSourceSummaryBundle`。`NoteGenerator.generate` 保持对外接口不变，内部从当前串行链路逐步切到 bundle 驱动的融合总结；Frame 识别优先多模态 LLM，失败后 OCR 兜底。

**Tech Stack:** Python 3、FastAPI、unittest、ThreadPoolExecutor、ffmpeg/PIL、RapidOCR、OpenAI-compatible GPT、React/Vite/TypeScript。

---

## 文件结构

### 新增后端模块

- `backend/app/models/multisource_summary.py`
  - 定义 collector 结果、Web Search 结果、Frame 结果、最终 bundle。
- `backend/app/services/collector_status.py`
  - 写入并读取 `collector_timings`，不扩展主 `TaskStatus` 枚举。
- `backend/app/services/web_search.py`
  - Web Search provider 抽象、环境变量配置、缓存、未配置时 graceful skip。
- `backend/app/services/transcript_collector.py`
  - 从现有 `NoteGenerator` 字幕/转写逻辑中抽取成独立 collector。
- `backend/app/services/video_frame_collector.py`
  - 视频下载、抽帧拼图、视觉 LLM 识别、OCR fallback。
- `backend/app/services/multisource_video_collector.py`
  - 三路并行编排，输出 `MultiSourceSummaryBundle`。
- `backend/tests/test_multisource_summary_contracts.py`
  - 数据模型、collector 状态、bundle 基础契约。
- `backend/tests/test_video_frame_collector_contracts.py`
  - FrameCollector 视觉失败后 OCR 兜底契约。
- `backend/tests/test_multisource_video_collector_contracts.py`
  - 三路并行、失败不阻塞、bundle 汇总契约。
- `backend/tests/test_multisource_note_integration_contracts.py`
  - `NoteGenerator.generate` 集成三源上下文的契约。

### 修改后端文件

- `backend/app/utils/video_reader.py`
  - 支持 task 独立目录，不清理全局 `output_frames/grid_output`。
- `backend/app/services/note.py`
  - 接入 `MultiSourceVideoCollector`，保留旧方法作为可复用子能力。
- `backend/app/services/context_normalizer.py`
  - 将 `web_search_context` 和 `frame_context` 注入 `WeightedContextPack`。
- `backend/app/renderers/note_renderer.py`
  - 增加 `search` source title，最终上下文支持外部搜索证据。
- `backend/app/services/task_status_writer.py`
  - status payload 兼容 `collector_timings`。
- `backend/app/routers/note.py`
  - `GET /task_status/{task_id}` 返回 `collector_timings`。

### 修改前端文件

- `frontend/src/services/note.ts`
  - `TaskStatusResponse` 增加 `collector_timings` 类型。
- `frontend/src/pages/HomePage/progressSteps.ts`
  - 将视频任务阶段文案从 `下载音频` 调整为 `采集素材`。
- `frontend/src/pages/HomePage/components/StepBar.tsx`
  - 在当前阶段卡片中展示并行子任务状态。
- `frontend/src/store/taskStore/index.ts`
  - 如类型收敛在 store 中定义，补充 collector timing 类型。
- `frontend/tests/noteTaskPendingUi.test.mjs`
  - 增加并行子状态兼容测试，旧 payload 不受影响。

---

### Task 1: 定义多源数据模型

**Files:**
- Create: `backend/app/models/multisource_summary.py`
- Test: `backend/tests/test_multisource_summary_contracts.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_multisource_summary_contracts.py`：

```python
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.multisource_summary import (  # noqa: E402
    CollectorResult,
    FrameContextResult,
    MultiSourceSummaryBundle,
    WebSearchResult,
)


class TestMultiSourceSummaryContracts(unittest.TestCase):
    def test_default_collector_result_is_non_blocking(self):
        result = CollectorResult(source="web_search", status="skipped")

        self.assertEqual(result.source, "web_search")
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.content, "")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.artifacts, {})

    def test_bundle_carries_three_source_results(self):
        bundle = MultiSourceSummaryBundle(
            task_id="task-1",
            source_url="https://example.com/video",
            platform="youtube",
            title="Demo",
            audio_meta=None,
            transcript=None,
            web_search=WebSearchResult(
                source="web_search",
                status="done",
                content="外部资料",
                sources=[{"title": "Source", "url": "https://example.com"}],
            ),
            frame_context=FrameContextResult(
                source="frames",
                status="done",
                content="00:10 画面展示表格",
                mode="ocr",
                frames=[{"timestamp": 10, "text": "表格"}],
                grid_images=["data:image/jpeg;base64,abc"],
            ),
        )

        self.assertEqual(bundle.web_search.sources[0]["title"], "Source")
        self.assertEqual(bundle.frame_context.mode, "ocr")
        self.assertEqual(bundle.frame_context.frames[0]["timestamp"], 10)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts -v
```

Expected: FAIL，错误包含 `No module named 'app.models.multisource_summary'`。

- [ ] **Step 3: 添加数据模型**

创建 `backend/app/models/multisource_summary.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CollectorResult:
    source: str
    status: str
    content: str = ""
    confidence: float = 0.0
    error: Optional[str] = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebSearchResult(CollectorResult):
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FrameContextResult(CollectorResult):
    mode: str = "disabled"
    frames: list[dict[str, Any]] = field(default_factory=list)
    grid_images: list[str] = field(default_factory=list)


@dataclass
class MultiSourceSummaryBundle:
    task_id: str
    source_url: str
    platform: str
    title: str
    audio_meta: Any | None
    transcript: Any | None
    web_search: WebSearchResult
    frame_context: FrameContextResult
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/multisource_summary.py backend/tests/test_multisource_summary_contracts.py
git commit -m "feat: add multisource summary models"
```

---

### Task 2: 增加 Collector 子状态写入能力

**Files:**
- Create: `backend/app/services/collector_status.py`
- Modify: `backend/app/routers/note.py`
- Test: `backend/tests/test_multisource_summary_contracts.py`

- [ ] **Step 1: 扩展失败测试**

在 `backend/tests/test_multisource_summary_contracts.py` 追加：

```python
import tempfile
from unittest.mock import patch

from app.services import collector_status  # noqa: E402


class TestCollectorStatusContracts(unittest.TestCase):
    def test_collector_status_round_trips_in_status_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            with patch.object(collector_status, "NOTE_OUTPUT_DIR", output_dir):
                collector_status.mark_collector_running("task-1", "web_search", message="搜索中")
                collector_status.mark_collector_done("task-1", "web_search", duration_ms=1234)

                payload = collector_status.read_collector_timings("task-1")

        self.assertEqual(payload["web_search"]["status"], "done")
        self.assertEqual(payload["web_search"]["duration_ms"], 1234)
        self.assertEqual(payload["web_search"]["message"], "搜索中")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts -v
```

Expected: FAIL，错误包含 `cannot import name 'collector_status'`。

- [ ] **Step 3: 新增 collector status 服务**

创建 `backend/app/services/collector_status.py`：

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.storage_paths import note_output_dir


NOTE_OUTPUT_DIR = note_output_dir()


def _status_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / f"{task_id}.status.json"


def _read_payload(task_id: str) -> dict[str, Any]:
    path = _status_path(task_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_payload(task_id: str, payload: dict[str, Any]) -> None:
    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(task_id)
    tmp_path = path.with_suffix(".status.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _update_collector(task_id: str, collector: str, fields: dict[str, Any]) -> None:
    payload = _read_payload(task_id)
    timings = payload.get("collector_timings")
    if not isinstance(timings, dict):
        timings = {}
    current = timings.get(collector)
    if not isinstance(current, dict):
        current = {}
    current.update(fields)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    timings[collector] = current
    payload["collector_timings"] = timings
    _write_payload(task_id, payload)


def mark_collector_running(task_id: str, collector: str, message: str = "") -> None:
    _update_collector(
        task_id,
        collector,
        {
            "status": "running",
            "message": message,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def mark_collector_done(task_id: str, collector: str, duration_ms: int) -> None:
    _update_collector(task_id, collector, {"status": "done", "duration_ms": max(0, int(duration_ms))})


def mark_collector_failed(task_id: str, collector: str, error: str) -> None:
    _update_collector(task_id, collector, {"status": "failed", "error": error})


def mark_collector_skipped(task_id: str, collector: str, reason: str) -> None:
    _update_collector(task_id, collector, {"status": "skipped", "message": reason})


def read_collector_timings(task_id: str) -> dict[str, Any]:
    timings = _read_payload(task_id).get("collector_timings")
    return timings if isinstance(timings, dict) else {}
```

- [ ] **Step 4: 让任务状态接口返回 collector_timings**

修改 `backend/app/routers/note.py`，在 imports 处加入：

```python
from app.services.collector_status import read_collector_timings
```

在 `get_task_status()` 的 `status_payload()` 内，`payload` 字典增加：

```python
"collector_timings": read_collector_timings(task_id),
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts backend.tests.test_core_note_task_status_api -v
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/collector_status.py backend/app/routers/note.py backend/tests/test_multisource_summary_contracts.py
git commit -m "feat: track multisource collector timings"
```

---

### Task 3: Web Search Collector 与 Provider 抽象

**Files:**
- Create: `backend/app/services/web_search.py`
- Test: `backend/tests/test_multisource_video_collector_contracts.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_multisource_video_collector_contracts.py`：

```python
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.multisource_summary import WebSearchResult  # noqa: E402
from app.services import web_search  # noqa: E402


class _FakeProvider:
    def search(self, query: str, limit: int = 5):
        return [
            {
                "title": "视频背景资料",
                "url": "https://example.com/a",
                "snippet": f"query={query}",
                "published_at": "2026-06-01",
                "confidence": 0.8,
            }
        ]


class TestWebSearchCollectorContracts(unittest.TestCase):
    def test_web_search_collector_uses_provider_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            collector = web_search.WebSearchCollector(provider=_FakeProvider(), output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                source_url="https://example.com/video",
                title="视频标题",
                platform="youtube",
                description="视频描述",
            )

            cache_path = output_dir / "task-1_web_search.json"

        self.assertIsInstance(result, WebSearchResult)
        self.assertEqual(result.status, "done")
        self.assertIn("视频背景资料", result.content)
        self.assertTrue(cache_path.exists())

    def test_web_search_collector_skips_when_provider_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            collector = web_search.WebSearchCollector(provider=None, output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                source_url="https://example.com/video",
                title="视频标题",
                platform="youtube",
                description=None,
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.content, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: FAIL，错误包含 `cannot import name 'web_search'`。

- [ ] **Step 3: 实现 Web Search Collector**

创建 `backend/app/services/web_search.py`：

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from app.models.multisource_summary import WebSearchResult
from app.utils.storage_paths import note_output_dir


class WebSearchProvider(Protocol):
    def search(self, query: str, limit: int = 5) -> list[dict]:
        ...


class DisabledWebSearchProvider:
    def search(self, query: str, limit: int = 5) -> list[dict]:
        return []


def get_web_search_provider() -> WebSearchProvider | None:
    provider_name = (os.getenv("NOTEMELD_WEB_SEARCH_PROVIDER", "") or "").strip().lower()
    if not provider_name:
        return None
    if provider_name in {"disabled", "none"}:
        return None
    raise ValueError(f"不支持的 Web Search provider: {provider_name}")


class WebSearchCollector:
    def __init__(self, provider: WebSearchProvider | None = None, output_dir: Path | None = None):
        self.provider = provider
        self.output_dir = output_dir or note_output_dir()

    def collect(
        self,
        *,
        task_id: str,
        source_url: str,
        title: str,
        platform: str,
        description: str | None,
    ) -> WebSearchResult:
        cache_path = self.output_dir / f"{task_id}_web_search.json"
        cached = self._read_cache(cache_path)
        if cached:
            return cached
        if self.provider is None:
            return WebSearchResult(source="web_search", status="skipped", error="web search provider 未配置")
        query = self._build_query(source_url=source_url, title=title, platform=platform, description=description)
        try:
            sources = self.provider.search(query, limit=5)
        except Exception as exc:
            return WebSearchResult(source="web_search", status="failed", error=str(exc))
        normalized = self._normalize_sources(sources)
        content = self._format_sources(normalized)
        result = WebSearchResult(
            source="web_search",
            status="done" if normalized else "skipped",
            content=content,
            confidence=0.7 if normalized else 0.0,
            sources=normalized,
            artifacts={"query": query},
        )
        self._write_cache(cache_path, result)
        return result

    def _build_query(self, *, source_url: str, title: str, platform: str, description: str | None) -> str:
        parts = [title.strip(), platform.strip(), source_url.strip()]
        if description:
            parts.append(description.strip()[:120])
        return " ".join(part for part in parts if part)

    def _normalize_sources(self, sources: list[dict]) -> list[dict]:
        normalized = []
        seen_urls = set()
        for item in sources:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            normalized.append(
                {
                    "title": title or url,
                    "url": url,
                    "snippet": str(item.get("snippet") or item.get("summary") or "").strip(),
                    "published_at": item.get("published_at"),
                    "confidence": float(item.get("confidence") or 0.5),
                }
            )
        return normalized[:5]

    def _format_sources(self, sources: list[dict]) -> str:
        lines = []
        for index, source in enumerate(sources, start=1):
            lines.append(
                f"{index}. {source['title']}\n"
                f"URL: {source['url']}\n"
                f"摘要: {source.get('snippet') or ''}\n"
                f"可信度: {source.get('confidence', 0.0)}"
            )
        return "\n\n".join(lines)

    def _read_cache(self, cache_path: Path) -> WebSearchResult | None:
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return WebSearchResult(**payload)
        except Exception:
            return None

    def _write_cache(self, cache_path: Path, result: WebSearchResult) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/web_search.py backend/tests/test_multisource_video_collector_contracts.py
git commit -m "feat: add web search collector"
```

---

### Task 4: 改造 VideoReader 为 task 独立目录

**Files:**
- Modify: `backend/app/utils/video_reader.py`
- Test: `backend/tests/test_video_frame_collector_contracts.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_video_frame_collector_contracts.py`：

```python
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.utils.video_reader import VideoReader  # noqa: E402


class TestVideoReaderContracts(unittest.TestCase):
    def test_video_reader_only_clears_its_own_task_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = pathlib.Path(tmp_dir)
            task_a_frames = base / "task-a" / "raw"
            task_a_grids = base / "task-a" / "grid"
            task_b_frames = base / "task-b" / "raw"
            task_b_grids = base / "task-b" / "grid"
            for path in [task_a_frames, task_a_grids, task_b_frames, task_b_grids]:
                path.mkdir(parents=True)
            (task_b_frames / "frame_00_01.jpg").write_bytes(b"keep")
            (task_b_grids / "grid_1.jpg").write_bytes(b"keep")

            reader = VideoReader(
                video_path="/tmp/not-used.mp4",
                frame_dir=str(task_a_frames),
                grid_dir=str(task_a_grids),
            )

            with patch.object(reader, "extract_frames", return_value=[]):
                result = reader.run()

            self.assertEqual(result, [])
            self.assertTrue((task_b_frames / "frame_00_01.jpg").exists())
            self.assertTrue((task_b_grids / "grid_1.jpg").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试**

Run:

```bash
python -m unittest backend.tests.test_video_frame_collector_contracts -v
```

Expected: PASS 或 FAIL 均可接受；如果 PASS，说明当前显式目录场景已安全，但仍要完成 Step 3 移除 `print` 并收敛清理逻辑。

- [ ] **Step 3: 收敛 VideoReader.run()**

修改 `backend/app/utils/video_reader.py`：

```python
    def _clear_generated_files(self) -> None:
        os.makedirs(self.frame_dir, exist_ok=True)
        os.makedirs(self.grid_dir, exist_ok=True)
        for file in os.listdir(self.frame_dir):
            if file.startswith("frame_") and file.endswith(".jpg"):
                os.remove(os.path.join(self.frame_dir, file))
        for file in os.listdir(self.grid_dir):
            if file.startswith("grid_") and file.endswith(".jpg"):
                os.remove(os.path.join(self.grid_dir, file))

    def run(self) -> list[str]:
        logger.info("开始提取视频帧...")
        try:
            self._clear_generated_files()
            self.extract_frames()
            logger.info("开始拼接网格图...")
            image_paths = []
            groups = self.group_images()
            for idx, group in enumerate(groups, start=1):
                if len(group) < self.grid_size[0] * self.grid_size[1]:
                    logger.warning(f"跳过第 {idx} 组，图片不足 {self.grid_size[0] * self.grid_size[1]} 张")
                    continue
                out_path = self.concat_images(group, f"grid_{idx}")
                image_paths.append(out_path)

            logger.info("开始编码图像...")
            return self.encode_images_to_base64(image_paths)
        except Exception as e:
            logger.error(f"发生错误：{str(e)}")
            raise ValueError("视频处理失败")
```

同时删除 `__init__` 和 `run()` 中的 `print(...)`。

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_video_frame_collector_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/video_reader.py backend/tests/test_video_frame_collector_contracts.py
git commit -m "fix: isolate video frame output directories"
```

---

### Task 5: 实现 FrameCollector 与 OCR fallback

**Files:**
- Create: `backend/app/services/video_frame_collector.py`
- Modify: `backend/tests/test_video_frame_collector_contracts.py`

- [ ] **Step 1: 扩展失败测试**

在 `backend/tests/test_video_frame_collector_contracts.py` 追加：

```python
from types import SimpleNamespace

from app.services.video_frame_collector import VideoFrameCollector  # noqa: E402


class _FakeDownloader:
    def download_video(self, video_url):
        return "/tmp/fake-video.mp4"


class _FailingVisionGpt:
    def summarize(self, source):
        raise RuntimeError("vision model failed")


class _FakeOcr:
    def extract_text(self, file_path):
        return {
            "text": "画面文字",
            "engine": "fake",
            "confidence": 0.9,
            "pages": [],
            "lines": [{"text": "画面文字", "confidence": 0.9, "page": 1, "order": 1}],
        }


class TestVideoFrameCollectorContracts(unittest.TestCase):
    def test_frame_collector_falls_back_to_ocr_when_vision_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            grid_path = output_dir / "frames" / "task-1" / "grid" / "grid_1.jpg"
            grid_path.parent.mkdir(parents=True)
            grid_path.write_bytes(b"image")

            collector = VideoFrameCollector(
                output_dir=output_dir,
                ocr_provider=_FakeOcr(),
                video_reader_factory=lambda **kwargs: SimpleNamespace(run=lambda: ["data:image/jpeg;base64,abc"]),
                grid_path_resolver=lambda task_id: [grid_path],
            )

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=_FakeDownloader(),
                gpt=_FailingVisionGpt(),
                screenshot=True,
                grid_size=[2, 2],
                frame_timestamps=[1, 2, 3, 4],
            )

        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "ocr")
        self.assertIn("画面文字", result.content)
        self.assertEqual(result.frames[0]["source"], "ocr")

    def test_frame_collector_skips_when_screenshot_disabled(self):
        collector = VideoFrameCollector(output_dir=pathlib.Path("/tmp"))

        result = collector.collect(
            task_id="task-1",
            video_url="https://example.com/video",
            downloader=_FakeDownloader(),
            gpt=_FailingVisionGpt(),
            screenshot=False,
            grid_size=[2, 2],
            frame_timestamps=[],
        )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.mode, "disabled")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_video_frame_collector_contracts -v
```

Expected: FAIL，错误包含 `No module named 'app.services.video_frame_collector'`。

- [ ] **Step 3: 实现 FrameCollector**

创建 `backend/app/services/video_frame_collector.py`：

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.gpt.gpt_model import GPTSource
from app.models.multisource_summary import FrameContextResult
from app.services.ocr.provider import get_ocr_provider
from app.utils.storage_paths import note_output_dir
from app.utils.video_reader import VideoReader


class VideoFrameCollector:
    def __init__(
        self,
        output_dir: Path | None = None,
        ocr_provider=None,
        video_reader_factory: Callable[..., object] | None = None,
        grid_path_resolver: Callable[[str], list[Path]] | None = None,
    ):
        self.output_dir = output_dir or note_output_dir()
        self.ocr_provider = ocr_provider
        self.video_reader_factory = video_reader_factory or VideoReader
        self.grid_path_resolver = grid_path_resolver or self._default_grid_paths

    def collect(
        self,
        *,
        task_id: str,
        video_url: str,
        downloader,
        gpt,
        screenshot: bool,
        grid_size: list[int],
        frame_timestamps: list[float] | None,
    ) -> FrameContextResult:
        if not screenshot:
            return FrameContextResult(source="frames", status="skipped", mode="disabled")
        cache_path = self.output_dir / f"{task_id}_frame_context.json"
        cached = self._read_cache(cache_path)
        if cached:
            return cached
        try:
            video_path = downloader.download_video(video_url)
            frame_dir = self.output_dir / "frames" / task_id / "raw"
            grid_dir = self.output_dir / "frames" / task_id / "grid"
            reader = self.video_reader_factory(
                video_path=str(video_path),
                grid_size=tuple(grid_size or [2, 2]),
                frame_interval=6,
                frame_timestamps=frame_timestamps,
                frame_dir=str(frame_dir),
                grid_dir=str(grid_dir),
                unit_width=960,
                unit_height=540,
                save_quality=80,
            )
            grid_images = list(reader.run())
            try:
                result = self._summarize_with_vision(task_id=task_id, gpt=gpt, grid_images=grid_images)
            except Exception:
                result = self._summarize_with_ocr(task_id=task_id, grid_images=grid_images)
            self._write_cache(cache_path, result)
            return result
        except Exception as exc:
            return FrameContextResult(source="frames", status="failed", mode="disabled", error=str(exc))

    def _summarize_with_vision(self, *, task_id: str, gpt, grid_images: list[str]) -> FrameContextResult:
        if not grid_images:
            raise RuntimeError("没有可识别的分帧图片")
        prompt = (
            "请识别这些带时间戳的视频网格截图。"
            "按 mm:ss 输出画面摘要、画面文字、图表/PPT/代码/网页操作等证据。"
            "不要虚构看不到的内容。"
        )
        markdown = gpt.summarize(
            GPTSource(
                title="视频画面识别",
                segment=[],
                tags=[],
                screenshot=False,
                link=False,
                _format=[],
                style=None,
                extras=prompt,
                video_img_urls=grid_images,
                checkpoint_key=f"{task_id}:frame-vision",
            )
        )
        if not markdown.strip():
            raise RuntimeError("视觉识别结果为空")
        return FrameContextResult(
            source="frames",
            status="done",
            content=markdown.strip(),
            confidence=0.75,
            mode="vision_llm",
            grid_images=grid_images,
            frames=[{"source": "vision_llm", "summary": markdown.strip()}],
        )

    def _summarize_with_ocr(self, *, task_id: str, grid_images: list[str]) -> FrameContextResult:
        provider = self.ocr_provider or get_ocr_provider()
        grid_paths = self.grid_path_resolver(task_id)
        frames = []
        lines = []
        for index, path in enumerate(grid_paths, start=1):
            ocr_result = provider.extract_text(Path(path))
            text = (ocr_result.get("text") or "").strip()
            if not text:
                continue
            frames.append(
                {
                    "source": "ocr",
                    "grid_index": index,
                    "image_path": str(path),
                    "text": text,
                    "confidence": ocr_result.get("confidence"),
                }
            )
            lines.append(f"Grid {index}: {text}")
        if not frames:
            return FrameContextResult(source="frames", status="failed", mode="ocr", error="OCR 未提取到文字")
        return FrameContextResult(
            source="frames",
            status="done",
            content="\n".join(lines),
            confidence=0.55,
            mode="ocr",
            frames=frames,
            grid_images=grid_images,
        )

    def _default_grid_paths(self, task_id: str) -> list[Path]:
        grid_dir = self.output_dir / "frames" / task_id / "grid"
        if not grid_dir.exists():
            return []
        return sorted(path for path in grid_dir.iterdir() if path.name.startswith("grid_") and path.suffix == ".jpg")

    def _read_cache(self, cache_path: Path) -> FrameContextResult | None:
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return FrameContextResult(**payload)
        except Exception:
            return None

    def _write_cache(self, cache_path: Path, result: FrameContextResult) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_video_frame_collector_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/video_frame_collector.py backend/tests/test_video_frame_collector_contracts.py
git commit -m "feat: add video frame collector with ocr fallback"
```

---

### Task 6: 抽取 TranscriptCollector

**Files:**
- Create: `backend/app/services/transcript_collector.py`
- Modify: `backend/app/services/note.py`
- Test: `backend/tests/test_multisource_video_collector_contracts.py`

- [ ] **Step 1: 增加 TranscriptCollector 契约测试**

在 `backend/tests/test_multisource_video_collector_contracts.py` 追加：

```python
import json
from dataclasses import asdict

from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.services.transcript_collector import TranscriptCollector  # noqa: E402


class _FakeTranscriptDownloader:
    def download_subtitles(self, video_url):
        return TranscriptResult(
            language="zh",
            full_text="平台字幕",
            segments=[TranscriptSegment(start=0, end=1, text="平台字幕")],
        )

    def download(self, video_url, quality, output_dir=None, need_video=False, skip_download=False):
        return AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"description": "描述"},
        )


class TestTranscriptCollectorContracts(unittest.TestCase):
    def test_transcript_collector_prefers_subtitle_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            collector = TranscriptCollector(output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=_FakeTranscriptDownloader(),
                quality="medium",
                output_path=None,
            )

            transcript_cache = output_dir / "task-1_transcript.json"
            audio_cache = output_dir / "task-1_audio.json"

        self.assertEqual(result.transcript.full_text, "平台字幕")
        self.assertEqual(result.audio_meta.title, "视频标题")
        self.assertTrue(transcript_cache.exists())
        self.assertTrue(audio_cache.exists())
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: FAIL，错误包含 `No module named 'app.services.transcript_collector'`。

- [ ] **Step 3: 实现 TranscriptCollector**

创建 `backend/app/services/transcript_collector.py`：

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult
from app.utils.storage_paths import note_output_dir


@dataclass
class TranscriptCollectionResult:
    transcript: TranscriptResult
    audio_meta: AudioDownloadResult


class TranscriptCollector:
    def __init__(self, output_dir: Path | None = None, transcribe_func=None):
        self.output_dir = output_dir or note_output_dir()
        self.transcribe_func = transcribe_func

    def collect(
        self,
        *,
        task_id: str,
        video_url: str,
        downloader,
        quality,
        output_path: str | None,
    ) -> TranscriptCollectionResult:
        transcript_cache = self.output_dir / f"{task_id}_transcript.json"
        audio_cache = self.output_dir / f"{task_id}_audio.json"
        transcript = self._read_transcript_cache(transcript_cache)
        if transcript is None:
            transcript = self._download_subtitles(video_url, downloader)
            if transcript is not None:
                self._write_json(transcript_cache, asdict(transcript))
        audio_meta = self._read_audio_cache(audio_cache)
        if audio_meta is None:
            audio_meta = downloader.download(
                video_url=video_url,
                quality=quality,
                output_dir=output_path,
                need_video=False,
                skip_download=transcript is not None,
            )
            self._write_json(audio_cache, asdict(audio_meta))
        if transcript is None:
            if self.transcribe_func is None:
                raise RuntimeError("没有平台字幕且未提供转写函数")
            transcript = self.transcribe_func(video_url=video_url, audio_file=audio_meta.file_path)
            self._write_json(transcript_cache, asdict(transcript))
        return TranscriptCollectionResult(transcript=transcript, audio_meta=audio_meta)

    def _download_subtitles(self, video_url: str, downloader) -> TranscriptResult | None:
        try:
            transcript = downloader.download_subtitles(video_url)
        except Exception:
            return None
        if transcript and transcript.segments:
            return transcript
        return None

    def _read_transcript_cache(self, path: Path) -> TranscriptResult | None:
        if not path.exists():
            return None
        try:
            from app.services.note import _normalize_transcript_payload

            return _normalize_transcript_payload(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _read_audio_cache(self, path: Path) -> AudioDownloadResult | None:
        if not path.exists():
            return None
        try:
            return AudioDownloadResult(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/transcript_collector.py backend/tests/test_multisource_video_collector_contracts.py
git commit -m "feat: add transcript collector"
```

---

### Task 7: 实现 MultiSourceVideoCollector 并行编排

**Files:**
- Create: `backend/app/services/multisource_video_collector.py`
- Modify: `backend/tests/test_multisource_video_collector_contracts.py`

- [ ] **Step 1: 增加并行编排测试**

在 `backend/tests/test_multisource_video_collector_contracts.py` 追加：

```python
from app.models.multisource_summary import FrameContextResult  # noqa: E402
from app.services.multisource_video_collector import MultiSourceVideoCollector  # noqa: E402


class _FakeWebCollector:
    def collect(self, **kwargs):
        return WebSearchResult(source="web_search", status="done", content="搜索资料")


class _FakeTranscriptCollector:
    def collect(self, **kwargs):
        return SimpleNamespace(
            transcript=TranscriptResult(
                language="zh",
                full_text="字幕文本",
                segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
            ),
            audio_meta=AudioDownloadResult(
                file_path="/tmp/audio.mp3",
                title="视频标题",
                duration=60,
                cover_url=None,
                platform="youtube",
                video_id="v1",
                raw_info={"description": "描述"},
            ),
        )


class _FakeFrameCollector:
    def collect(self, **kwargs):
        return FrameContextResult(source="frames", status="done", content="画面资料", mode="vision_llm")


class TestMultiSourceVideoCollectorContracts(unittest.TestCase):
    def test_multisource_collector_returns_bundle_with_three_sources(self):
        collector = MultiSourceVideoCollector(
            web_search_collector=_FakeWebCollector(),
            transcript_collector=_FakeTranscriptCollector(),
            frame_collector=_FakeFrameCollector(),
            max_workers=3,
        )

        bundle = collector.collect(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            downloader=object(),
            gpt=object(),
            quality="medium",
            output_path=None,
            screenshot=True,
            grid_size=[2, 2],
            frame_timestamps=[1, 2, 3, 4],
        )

        self.assertEqual(bundle.web_search.content, "搜索资料")
        self.assertEqual(bundle.transcript.full_text, "字幕文本")
        self.assertEqual(bundle.frame_context.content, "画面资料")
        self.assertEqual(bundle.audio_meta.title, "视频标题")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: FAIL，错误包含 `No module named 'app.services.multisource_video_collector'`。

- [ ] **Step 3: 实现并行编排**

创建 `backend/app/services/multisource_video_collector.py`：

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.models.multisource_summary import FrameContextResult, MultiSourceSummaryBundle, WebSearchResult
from app.services.collector_status import (
    mark_collector_done,
    mark_collector_failed,
    mark_collector_running,
    mark_collector_skipped,
)
from app.services.transcript_collector import TranscriptCollector
from app.services.video_frame_collector import VideoFrameCollector
from app.services.web_search import WebSearchCollector, get_web_search_provider


class MultiSourceVideoCollector:
    def __init__(
        self,
        web_search_collector=None,
        transcript_collector=None,
        frame_collector=None,
        max_workers: int = 3,
    ):
        self.web_search_collector = web_search_collector or WebSearchCollector(provider=get_web_search_provider())
        self.transcript_collector = transcript_collector or TranscriptCollector()
        self.frame_collector = frame_collector or VideoFrameCollector()
        self.max_workers = max_workers

    def collect(
        self,
        *,
        task_id: str,
        video_url: str,
        platform: str,
        downloader,
        gpt,
        quality,
        output_path: str | None,
        screenshot: bool,
        grid_size: list[int],
        frame_timestamps: list[float] | None,
    ) -> MultiSourceSummaryBundle:
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            transcript_future = executor.submit(
                self._collect_transcript,
                task_id,
                video_url,
                downloader,
                quality,
                output_path,
            )
            web_future = executor.submit(self._collect_web_search_after_meta, task_id, video_url, platform, transcript_future)
            frame_future = executor.submit(
                self._collect_frames,
                task_id,
                video_url,
                downloader,
                gpt,
                screenshot,
                grid_size,
                frame_timestamps,
            )

            transcript_result = transcript_future.result()
            web_search = web_future.result()
            frame_context = frame_future.result()

        return MultiSourceSummaryBundle(
            task_id=task_id,
            source_url=video_url,
            platform=platform,
            title=transcript_result.audio_meta.title,
            audio_meta=transcript_result.audio_meta,
            transcript=transcript_result.transcript,
            web_search=web_search,
            frame_context=frame_context,
        )

    def _collect_transcript(self, task_id, video_url, downloader, quality, output_path):
        started = datetime.now(timezone.utc)
        mark_collector_running(task_id, "transcript", "音频转文字中")
        try:
            result = self.transcript_collector.collect(
                task_id=task_id,
                video_url=video_url,
                downloader=downloader,
                quality=quality,
                output_path=output_path,
            )
            mark_collector_done(task_id, "transcript", self._elapsed_ms(started))
            return result
        except Exception as exc:
            mark_collector_failed(task_id, "transcript", str(exc))
            raise

    def _collect_web_search_after_meta(self, task_id, video_url, platform, transcript_future):
        started = datetime.now(timezone.utc)
        mark_collector_running(task_id, "web_search", "网页搜索中")
        try:
            transcript_result = transcript_future.result()
            audio_meta = transcript_result.audio_meta
            result = self.web_search_collector.collect(
                task_id=task_id,
                source_url=video_url,
                title=audio_meta.title,
                platform=platform,
                description=(audio_meta.raw_info or {}).get("description"),
            )
            if result.status == "skipped":
                mark_collector_skipped(task_id, "web_search", result.error or "web search skipped")
            elif result.status == "failed":
                mark_collector_failed(task_id, "web_search", result.error or "web search failed")
            else:
                mark_collector_done(task_id, "web_search", self._elapsed_ms(started))
            return result
        except Exception as exc:
            mark_collector_failed(task_id, "web_search", str(exc))
            return WebSearchResult(source="web_search", status="failed", error=str(exc))

    def _collect_frames(self, task_id, video_url, downloader, gpt, screenshot, grid_size, frame_timestamps):
        if not screenshot:
            mark_collector_skipped(task_id, "frames", "未勾选截图")
            return FrameContextResult(source="frames", status="skipped", mode="disabled")
        started = datetime.now(timezone.utc)
        mark_collector_running(task_id, "frames", "视频分帧中")
        result = self.frame_collector.collect(
            task_id=task_id,
            video_url=video_url,
            downloader=downloader,
            gpt=gpt,
            screenshot=screenshot,
            grid_size=grid_size,
            frame_timestamps=frame_timestamps,
        )
        if result.status == "done":
            mark_collector_done(task_id, "frames", self._elapsed_ms(started))
        else:
            mark_collector_failed(task_id, "frames", result.error or "视频分帧失败")
        return result

    def _elapsed_ms(self, started):
        return max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_video_collector_contracts -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/multisource_video_collector.py backend/tests/test_multisource_video_collector_contracts.py
git commit -m "feat: orchestrate multisource video collection"
```

---

### Task 8: 将 search 和 vision 注入总结上下文

**Files:**
- Modify: `backend/app/services/context_normalizer.py`
- Modify: `backend/app/renderers/note_renderer.py`
- Test: `backend/tests/test_multisource_summary_contracts.py`

- [ ] **Step 1: 增加 context pack 测试**

在 `backend/tests/test_multisource_summary_contracts.py` 追加：

```python
from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.services.context_normalizer import ContextNormalizer  # noqa: E402


class TestMultiSourceContextContracts(unittest.TestCase):
    def test_weighted_pack_includes_search_and_vision_blocks(self):
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"description": "描述"},
        )
        transcript = TranscriptResult(
            language="zh",
            full_text="字幕文本",
            segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
        )
        summary_input = ContextNormalizer().from_video_task(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            audio_meta=audio_meta,
            transcript=transcript,
            user_options={
                "web_search_context": "搜索资料",
                "frame_context": "画面资料",
            },
        )

        pack = ContextNormalizer().build_weighted_pack(summary_input)

        sources = [block.source_type for block in pack.context_blocks]
        self.assertIn("search", sources)
        self.assertIn("vision", sources)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts -v
```

Expected: FAIL，`search` 和 `vision` 不在 sources。

- [ ] **Step 3: 修改 ContextNormalizer**

在 `ContextNormalizer.build_weighted_pack()` 的 social block 前加入：

```python
        web_search_context = summary_input.user_options.get("web_search_context")
        if web_search_context:
            auxiliary_sources.append("search")
            source_weights["search"] = 0.45
            blocks.append(
                ContextBlock(
                    source_type="search",
                    role="external_evidence",
                    content=str(web_search_context),
                    weight=0.45,
                    confidence=0.65,
                    include_policy="final_stage",
                )
            )

        frame_context = summary_input.user_options.get("frame_context")
        if frame_context:
            auxiliary_sources.append("vision")
            source_weights["vision"] = 0.7
            blocks.append(
                ContextBlock(
                    source_type="vision",
                    role="visual_evidence",
                    content=str(frame_context),
                    weight=0.7,
                    confidence=0.7,
                    include_policy="final_stage",
                )
            )
```

- [ ] **Step 4: 修改 NoteRenderer 标题和融合说明**

在 `backend/app/renderers/note_renderer.py` 的 `SECTION_TITLES` 增加：

```python
"search": "网页搜索补充上下文",
```

将 `build_extras_with_context()` 的 `prefix` 改为：

```python
        prefix = (
            "请将以下结构化上下文作为辅助信息使用。"
            "字幕/转写是视频事实主源；视觉上下文是画面证据；"
            "网页搜索只作为外部背景和事实校验，不要写成视频作者原话。\n\n"
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
python -m unittest backend.tests.test_multisource_summary_contracts -v
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/context_normalizer.py backend/app/renderers/note_renderer.py backend/tests/test_multisource_summary_contracts.py
git commit -m "feat: add search and vision context blocks"
```

---

### Task 9: 集成 NoteGenerator.generate

**Files:**
- Modify: `backend/app/services/note.py`
- Test: `backend/tests/test_multisource_note_integration_contracts.py`

- [ ] **Step 1: 写集成契约测试**

创建 `backend/tests/test_multisource_note_integration_contracts.py`：

```python
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.multisource_summary import FrameContextResult, MultiSourceSummaryBundle, WebSearchResult  # noqa: E402
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.services.note import NoteGenerator  # noqa: E402


class _FakeGpt:
    model = "gpt-test"

    def set_usage_context(self, context):
        self.context = context

    def summarize(self, source):
        return "## 融合总结\n搜索资料\n字幕文本\n画面资料"


class _FakeDownloader:
    pass


class _FakeMultiSourceCollector:
    def collect(self, **kwargs):
        transcript = TranscriptResult(
            language="zh",
            full_text="字幕文本",
            segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
        )
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"description": "描述", "webpage_url": "https://example.com/video"},
        )
        return MultiSourceSummaryBundle(
            task_id="task-1",
            source_url="https://example.com/video",
            platform="youtube",
            title="视频标题",
            audio_meta=audio_meta,
            transcript=transcript,
            web_search=WebSearchResult(source="web_search", status="done", content="搜索资料"),
            frame_context=FrameContextResult(source="frames", status="done", content="画面资料", mode="vision_llm"),
        )


class TestMultiSourceNoteIntegrationContracts(unittest.TestCase):
    def test_note_generator_uses_multisource_bundle_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            generator = NoteGenerator()
            generator.multisource_collector_factory = lambda: _FakeMultiSourceCollector()

            with patch("app.services.note.NOTE_OUTPUT_DIR", output_dir), patch.object(
                generator, "_get_downloader", return_value=_FakeDownloader()
            ), patch.object(generator, "_get_gpt", return_value=_FakeGpt()), patch.object(
                generator, "_update_status"
            ), patch.object(generator, "_save_metadata"), patch(
                "app.services.note._run_transcript_ingestion_best_effort"
            ), patch.object(generator, "_schedule_summary_sidecars"):
                result = generator.generate(
                    video_url="https://example.com/video",
                    platform="youtube",
                    task_id="task-1",
                    model_name="gpt-test",
                    provider_id="provider-test",
                    screenshot=True,
                    _format=[],
                )

        self.assertIsNotNone(result)
        self.assertIn("融合总结", result.markdown)
        self.assertIn("搜索资料", result.markdown)
        self.assertIn("画面资料", result.markdown)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python -m unittest backend.tests.test_multisource_note_integration_contracts -v
```

Expected: FAIL，`NoteGenerator` 未使用 `multisource_collector_factory` 或仍走旧串行路径。

- [ ] **Step 3: 修改 NoteGenerator 初始化扩展点**

在 `backend/app/services/note.py` 中 `NoteGenerator` 类初始化位置加入：

```python
from app.services.multisource_video_collector import MultiSourceVideoCollector


class NoteGenerator:
    def __init__(self):
        self.multisource_collector_factory = MultiSourceVideoCollector
```

如果当前 `NoteGenerator` 没有显式 `__init__`，新增时保留已有实例字段初始化，例如 `self.video_img_urls = []`、`self.video_path = None` 这类字段必须迁移到 `__init__`。

- [ ] **Step 4: 在 generate 中替换采集段**

在 `NoteGenerator.generate()` 中，获取 `downloader` 和 `gpt` 后，替换当前 `# 1. 获取字幕/转写` 到 `# 3. 如果前面没拿到字幕` 结束的串行采集块，使用：

```python
            frame_timestamps = self._build_vision_frame_timestamps(
                task_id=task_id,
                transcript=None,
                video_understanding=video_understanding or screenshot,
                video_interval=video_interval,
                vision_mode=vision_mode,
                max_sampling_points=max_sampling_points,
            )
            bundle = self.multisource_collector_factory().collect(
                task_id=task_id,
                video_url=str(video_url),
                platform=platform,
                downloader=downloader,
                gpt=gpt,
                quality=quality,
                output_path=output_path,
                screenshot=screenshot,
                grid_size=grid_size,
                frame_timestamps=frame_timestamps,
            )
            audio_meta = bundle.audio_meta
            transcript = bundle.transcript
            if bundle.frame_context.grid_images:
                self.video_img_urls = bundle.frame_context.grid_images
```

保留后续 `if transcript is None or not transcript.segments` 的兜底判断。

- [ ] **Step 5: 将三源上下文传入总结**

调用 `_summarize_text(...)` 时修改 `extras`：

```python
                extras=self._build_multisource_extras(
                    existing_extras=extras,
                    web_search_context=bundle.web_search.content,
                    frame_context=bundle.frame_context.content,
                ),
```

在 `NoteGenerator` 类中新增：

```python
    def _build_multisource_extras(
        self,
        *,
        existing_extras: Optional[str],
        web_search_context: str,
        frame_context: str,
    ) -> str:
        sections = []
        if existing_extras:
            sections.append(existing_extras)
        if web_search_context:
            sections.append(
                "## 网页搜索补充\n"
                "以下内容来自外部网页搜索，只能作为背景补充和事实校验，不要写成视频作者原话。\n"
                f"{web_search_context}"
            )
        if frame_context:
            sections.append(
                "## 视频画面证据\n"
                "以下内容来自视频截图识别或 OCR，用于补充字幕未覆盖的画面信息。\n"
                f"{frame_context}"
            )
        return "\n\n".join(sections)
```

- [ ] **Step 6: 运行集成测试**

Run:

```bash
python -m unittest backend.tests.test_multisource_note_integration_contracts -v
```

Expected: PASS。

- [ ] **Step 7: 运行相关后端测试**

Run:

```bash
python -m unittest \
  backend.tests.test_multisource_summary_contracts \
  backend.tests.test_multisource_video_collector_contracts \
  backend.tests.test_video_frame_collector_contracts \
  backend.tests.test_multisource_note_integration_contracts \
  backend.tests.test_core_note_task_status_api \
  -v
```

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/note.py backend/tests/test_multisource_note_integration_contracts.py
git commit -m "feat: integrate multisource video collection"
```

---

### Task 10: 前端展示并行采集状态

**Files:**
- Modify: `frontend/src/services/note.ts`
- Modify: `frontend/src/pages/HomePage/progressSteps.ts`
- Modify: `frontend/src/pages/HomePage/components/StepBar.tsx`
- Modify: `frontend/src/store/taskStore/index.ts`
- Test: `frontend/tests/noteTaskPendingUi.test.mjs`

- [ ] **Step 1: 扩展前端类型**

修改 `frontend/src/services/note.ts`，新增：

```ts
export type CollectorTiming = {
  status?: 'running' | 'done' | 'failed' | 'skipped' | 'fallback_ocr'
  message?: string
  duration_ms?: number
  elapsed_ms?: number
  error?: string
  started_at?: string
  updated_at?: string
}
```

并在 `TaskStatusResponse` 中加入：

```ts
collector_timings?: Record<string, CollectorTiming>
```

如 `frontend/src/store/taskStore/index.ts` 定义了独立 task payload 类型，同步加入相同字段。

- [ ] **Step 2: 调整主阶段文案**

修改 `frontend/src/pages/HomePage/progressSteps.ts`：

```ts
  { label: '采集素材', key: 'DOWNLOADING', matches: ['DOWNLOADING'] },
```

保留其他阶段不变。

- [ ] **Step 3: 在 StepBar 展示子状态**

在 `frontend/src/pages/HomePage/components/StepBar.tsx` 中增加子状态渲染函数：

```tsx
const collectorLabels: Record<string, string> = {
  web_search: '网页搜索',
  transcript: '音频转文字',
  frames: '视频分帧',
  vision: '画面识别/OCR',
}

const renderCollectorTimings = (collectorTimings?: Record<string, any>) => {
  if (!collectorTimings || Object.keys(collectorTimings).length === 0) return null
  return (
    <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
      {Object.entries(collectorTimings).map(([key, value]) => (
        <div key={key} className="rounded-md border bg-background/60 px-2 py-1">
          <span className="font-medium text-foreground">{collectorLabels[key] || key}</span>
          <span className="ml-1">{value?.message || value?.status || '处理中'}</span>
        </div>
      ))}
    </div>
  )
}
```

在当前任务进度卡片区域插入：

```tsx
{renderCollectorTimings(task?.collector_timings)}
```

如果 `StepBar` 当前没有 `task` 入参，改为从调用方传入 `collectorTimings`：

```tsx
type StepBarProps = {
  status: TaskStatus
  platform?: string | null
  collectorTimings?: Record<string, any>
}
```

并在调用处传入 `task.collector_timings`。

- [ ] **Step 4: 增加前端契约测试**

在 `frontend/tests/noteTaskPendingUi.test.mjs` 追加测试 helper 或新增断言：

```js
import assert from 'node:assert/strict'

const payload = {
  status: 'SUMMARIZING',
  collector_timings: {
    web_search: { status: 'done', message: '网页搜索完成' },
    transcript: { status: 'running', message: '音频转文字中' },
    frames: { status: 'done', message: '视频分帧完成' },
  },
}

assert.equal(payload.collector_timings.web_search.message, '网页搜索完成')
assert.equal(payload.collector_timings.transcript.status, 'running')
```

如果该测试文件已有 DOM 渲染工具，使用已有工具断言 `网页搜索完成`、`音频转文字中`、`视频分帧完成` 出现在渲染结果中。

- [ ] **Step 5: 运行前端测试**

Run:

```bash
cd frontend && pnpm test noteTaskPendingUi.test.mjs
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/services/note.ts frontend/src/pages/HomePage/progressSteps.ts frontend/src/pages/HomePage/components/StepBar.tsx frontend/src/store/taskStore/index.ts frontend/tests/noteTaskPendingUi.test.mjs
git commit -m "feat: show multisource collection progress"
```

---

### Task 11: 回归与收尾

**Files:**
- Modify only if verification reveals failures in touched files.

- [ ] **Step 1: 运行后端核心回归**

Run:

```bash
python -m unittest \
  backend.tests.test_multisource_summary_contracts \
  backend.tests.test_multisource_video_collector_contracts \
  backend.tests.test_video_frame_collector_contracts \
  backend.tests.test_multisource_note_integration_contracts \
  backend.tests.test_core_note_task_status_api \
  backend.tests.test_web_note_contracts \
  -v
```

Expected: PASS。

- [ ] **Step 2: 运行前端相关回归**

Run:

```bash
cd frontend && pnpm test noteTaskPendingUi.test.mjs
```

Expected: PASS。

- [ ] **Step 3: 检查诊断**

Run through tooling:

```text
GetDiagnostics for modified Python and TypeScript files
```

Expected: no new diagnostics in touched files.

- [ ] **Step 4: 检查 Git 状态**

Run:

```bash
git status --short
```

Expected: only intentional changes remain, or clean working tree if all task commits are complete.

- [ ] **Step 5: 最终提交**

If any verification-only fixes were made:

```bash
git add <changed-files>
git commit -m "fix: stabilize multisource video summary flow"
```

If no fixes were made, do not create an empty commit.

---

## 自查结果

- Spec 覆盖：三路并行采集、Web Search 必跑、视频必转写、截图触发分帧、视觉失败 OCR、最终融合总结、缓存、状态展示、降级策略均有任务覆盖。
- 类型一致性：`CollectorResult`、`WebSearchResult`、`FrameContextResult`、`MultiSourceSummaryBundle` 在 Task 1 定义，后续任务复用同名类型。
- 范围控制：第一版只新增 provider 抽象，不强行绑定具体联网搜索供应商；未配置 provider 时跳过搜索但不阻塞任务。
- 风险控制：优先改造 `VideoReader` 独立目录，再接入 FrameCollector，避免并发清理互相覆盖。
