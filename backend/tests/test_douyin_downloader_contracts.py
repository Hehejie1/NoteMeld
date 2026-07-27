import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

sys.modules.setdefault("gmssl", SimpleNamespace(sm3=SimpleNamespace(), func=SimpleNamespace()))
abogus_module = type(sys)("app.downloaders.douyin_helper.abogus")
abogus_module.ABogus = type("ABogus", (), {"get_value": lambda self, params: "bogus"})
sys.modules.setdefault("app.downloaders.douyin_helper.abogus", abogus_module)

from app.downloaders.douyin_downloader import DouyinDownloader  # noqa: E402


class TestDouyinDownloaderContracts(unittest.TestCase):
    def test_direct_video_url_extracts_id_without_following_redirect(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)

        with patch("app.downloaders.douyin_downloader.requests.head") as head:
            video_id = downloader.extract_video_id("https://www.douyin.com/video/7617715093102431534")

        self.assertEqual(video_id, "7617715093102431534")
        head.assert_not_called()

    def test_short_url_uses_redirect_target_when_original_url_has_no_id(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)

        with patch(
            "app.downloaders.douyin_downloader.requests.head",
            return_value=SimpleNamespace(url="https://www.douyin.com/video/7617715093102431534"),
        ):
            video_id = downloader.extract_video_id("https://v.douyin.com/example/")

        self.assertEqual(video_id, "7617715093102431534")

    def test_short_url_redirecting_to_jingxuan_has_no_silent_video_id(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)

        with patch(
            "app.downloaders.douyin_downloader.requests.head",
            return_value=SimpleNamespace(url="https://www.douyin.com/jingxuan"),
        ):
            video_id = downloader.extract_video_id("https://v.douyin.com/example/")

        self.assertEqual(video_id, "")

    def test_fetch_video_info_rejects_empty_aweme_id_before_api_request(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)
        downloader.headers_config = {"User-Agent": "test"}
        downloader.extract_video_id = lambda _url: ""

        with patch("app.downloaders.douyin_downloader.requests.get") as get:
            with self.assertRaisesRegex(ValueError, "无法解析抖音作品 ID"):
                downloader.fetch_video_info("https://www.douyin.com/jingxuan")

        get.assert_not_called()

    def test_download_accepts_transcript_collector_skip_download_contract(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)

        with patch.object(
            downloader,
            "fetch_video_info",
            return_value={
                "aweme_detail": {
                    "aweme_id": "7617715093102431534",
                    "item_title": "Demo",
                    "caption": "Demo caption",
                    "music": {"play_url": {"uri": "https://example.com/audio.mp3"}},
                    "video": {
                        "duration": 123,
                        "cover": True,
                        "cover_original_scale": {"url_list": ["https://example.com/cover.jpg"]},
                    },
                    "video_tag": [{"tag_name": "tag"}],
                }
            },
        ), patch("app.downloaders.douyin_downloader.requests.get") as get, patch(
            "app.downloaders.douyin_downloader.open",
            create=True,
        ):
            get.return_value.content = b"audio"
            result = downloader.download(
                video_url="https://www.douyin.com/video/7617715093102431534",
                output_dir=None,
                quality="fast",
                need_video=False,
                skip_download=False,
            )

        self.assertEqual(result.video_id, "7617715093102431534")

    def test_download_falls_back_to_video_url_when_music_missing(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)
        downloader.headers_config = {"User-Agent": "test"}

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            downloader,
            "fetch_video_info",
            return_value={
                "aweme_detail": {
                    "aweme_id": "7617715093102431534",
                    "item_title": "Demo",
                    "caption": "Demo caption",
                    "video": {
                        "duration": 123,
                        "cover": True,
                        "cover_original_scale": {"url_list": ["https://example.com/cover.jpg"]},
                        "play_addr": {"url_list": ["https://example.com/video.mp4"]},
                    },
                    "video_tag": [],
                }
            },
        ), patch("app.downloaders.douyin_downloader.requests.get") as get:
            get.return_value.content = b"video"
            result = downloader.download(
                video_url="https://www.douyin.com/video/7617715093102431534",
                output_dir=tmp_dir,
                quality="fast",
                need_video=False,
                skip_download=False,
            )

        self.assertEqual(result.video_id, "7617715093102431534")
        self.assertTrue(result.file_path.endswith(".mp4"))
        self.assertEqual(get.call_args.args[0], "https://example.com/video.mp4")

    def test_download_ignores_bare_music_uri_and_uses_url_list(self):
        downloader = DouyinDownloader.__new__(DouyinDownloader)
        downloader.headers_config = {"User-Agent": "test"}

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
            downloader,
            "fetch_video_info",
            return_value={
                "aweme_detail": {
                    "aweme_id": "7624108287142743306",
                    "item_title": "Demo",
                    "caption": "Demo caption",
                    "music": {
                        "play_url": {
                            "uri": "v0d00fg10000d770t67og65n5fcf080g",
                            "url_list": ["https://example.com/audio.mp3"],
                        }
                    },
                    "video": {"duration": 150 * 60 * 1000},
                    "video_tag": [],
                }
            },
        ), patch("app.downloaders.douyin_downloader.requests.get") as get:
            get.return_value.content = b"audio"
            result = downloader.download(
                video_url="https://www.douyin.com/video/7624108287142743306",
                output_dir=tmp_dir,
                quality="fast",
                need_video=False,
                skip_download=False,
            )

        self.assertEqual(result.video_id, "7624108287142743306")
        self.assertEqual(get.call_args.args[0], "https://example.com/audio.mp3")


if __name__ == "__main__":
    unittest.main()
