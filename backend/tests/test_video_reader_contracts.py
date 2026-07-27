import contextlib
import io
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.modules.setdefault("ffmpeg", types.SimpleNamespace(probe=lambda _: {"format": {"duration": "0"}}))

from app.utils.video_reader import VideoReader  # noqa: E402


class _NoopVideoReader(VideoReader):
    def extract_frames(self, max_frames=1000):
        return []

    def group_images(self):
        return []

    def encode_images_to_base64(self, image_paths):
        return []


def _fake_app_dir(root: pathlib.Path):
    def factory(subdir: str = ""):
        path = root / subdir
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    return factory


class TestVideoReaderContracts(unittest.TestCase):
    def test_default_cleanup_keeps_other_video_reader_directories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            with patch("app.utils.video_reader.get_app_dir", side_effect=_fake_app_dir(root)):
                reader_a = _NoopVideoReader(video_path=str(root / "a.mp4"), grid_size=(1, 1))
                reader_b = _NoopVideoReader(video_path=str(root / "b.mp4"), grid_size=(1, 1))

                other_frame = pathlib.Path(reader_b.frame_dir) / "frame_00_00.jpg"
                other_grid = pathlib.Path(reader_b.grid_dir) / "grid_1.jpg"
                other_frame.parent.mkdir(parents=True, exist_ok=True)
                other_grid.parent.mkdir(parents=True, exist_ok=True)
                other_frame.write_text("other frame", encoding="utf-8")
                other_grid.write_text("other grid", encoding="utf-8")

                reader_a.run()

                self.assertTrue(other_frame.exists())
                self.assertTrue(other_grid.exists())

    def test_run_does_not_write_to_stdout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            stdout = io.StringIO()
            with patch("app.utils.video_reader.get_app_dir", side_effect=_fake_app_dir(root)):
                with contextlib.redirect_stdout(stdout):
                    reader = _NoopVideoReader(video_path=str(root / "video.mp4"), grid_size=(1, 1))
                    reader.run()

            self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
