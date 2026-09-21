import pathlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.services import collector_status  # noqa: E402
from app.services.collector_status import build_collector_timings  # noqa: E402


class TestCoreCollectorStatusContracts(unittest.TestCase):
    def test_build_collector_timings_filters_collection_stages(self):
        status_payload = {
            "stage_timings": {
                "PENDING": {"status": "done", "duration_ms": 3},
                "PARSING": {"status": "done", "duration_ms": 11},
                "DOWNLOADING": {"status": "done", "duration_ms": 22},
                "TRANSCRIBING": {"status": "running", "elapsed_ms": 33},
                "SUMMARIZING": {"status": "running", "elapsed_ms": 44},
            }
        }

        collector_timings = build_collector_timings(status_payload)

        self.assertEqual(
            collector_timings,
            {
                "PARSING": {"status": "done", "duration_ms": 11},
                "DOWNLOADING": {"status": "done", "duration_ms": 22},
                "TRANSCRIBING": {"status": "running", "elapsed_ms": 33},
            },
        )

    def test_build_collector_timings_prefers_explicit_collector_timings(self):
        status_payload = {
            "collector_timings": {
                "page": {"status": "done", "duration_ms": 15},
            },
            "stage_timings": {
                "PARSING": {"status": "done", "duration_ms": 11},
            },
        }

        self.assertEqual(
            build_collector_timings(status_payload),
            {"page": {"status": "done", "duration_ms": 15}},
        )

    def test_collector_status_write_helpers_round_trip_in_status_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            with patch.object(collector_status, "NOTE_OUTPUT_DIR", output_dir):
                collector_status.mark_collector_running("task-1", "web_search", message="网页搜索中")
                collector_status.mark_collector_done("task-1", "web_search", duration_ms=1234)
                collector_status.mark_collector_failed("task-1", "frames", error="视频分帧失败")
                collector_status.mark_collector_skipped("task-1", "vision", reason="未勾选截图")

                timings = collector_status.read_collector_timings("task-1")

        self.assertEqual(timings["web_search"]["status"], "done")
        self.assertEqual(timings["web_search"]["duration_ms"], 1234)
        self.assertEqual(timings["web_search"]["message"], "网页搜索中")
        self.assertEqual(timings["frames"]["status"], "failed")
        self.assertEqual(timings["frames"]["error"], "视频分帧失败")
        self.assertEqual(timings["vision"]["status"], "skipped")
        self.assertEqual(timings["vision"]["message"], "未勾选截图")

    def test_collector_status_concurrent_writes_do_not_raise_or_lose_timings(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            errors = []

            def write_status(index: int):
                try:
                    collector_status.mark_collector_running(
                        "task-concurrent",
                        f"collector-{index}",
                        message=f"collector {index}",
                    )
                except Exception as exc:  # pragma: no cover - assertion captures failures
                    errors.append(exc)

            with patch.object(collector_status, "NOTE_OUTPUT_DIR", output_dir):
                threads = [threading.Thread(target=write_status, args=(index,)) for index in range(20)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                timings = collector_status.read_collector_timings("task-concurrent")
                temp_files = list(output_dir.glob("*.tmp"))

        self.assertEqual(errors, [])
        self.assertEqual(len(timings), 20)
        self.assertEqual(temp_files, [])


if __name__ == "__main__":
    unittest.main()
