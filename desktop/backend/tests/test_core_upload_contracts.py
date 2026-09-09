import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.routers.note import _validate_upload_payload  # noqa: E402


class TestCoreUploadContracts(unittest.TestCase):
    def test_markdown_upload_allows_browser_octet_stream_content_type(self):
        _validate_upload_payload(
            "sample.md",
            "application/octet-stream",
            b"# Sample\n\nMarkdown content.",
        )


if __name__ == "__main__":
    unittest.main()
