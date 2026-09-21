#!/usr/bin/env python3
"""Static preview server with a small live-reload version endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path == "/__new_product_version":
            payload = json.dumps({"version": self.server.preview_version()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path.endswith(".html") or path == "/":
            self.serve_html_with_live_reload()
            return
        super().do_GET()

    def serve_html_with_live_reload(self) -> None:
        path = Path(self.translate_path(urlparse(self.path).path))
        if path.is_dir():
            path = path / "index.html"
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        body = path.read_text(encoding="utf-8")
        if "assets/live-reload.js" not in body:
            body = body.replace("</body>", '<script src="/assets/live-reload.js?v=20260914-1"></script></body>')
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


class PreviewServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], directory: Path):
        self.preview_directory = directory
        super().__init__(address, PreviewHandler)

    def preview_version(self) -> str:
        digest = hashlib.sha1()
        for path in sorted(self.preview_directory.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(str(path.relative_to(self.preview_directory)).encode())
            digest.update(str(stat.st_mtime_ns).encode())
            digest.update(str(stat.st_size).encode())
        return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    os.chdir(directory)
    server = PreviewServer(("127.0.0.1", args.port), directory)
    print(f"Serving NoteMeld preview on http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
