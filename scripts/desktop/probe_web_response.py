import argparse
import json
from pathlib import Path

import httpx


DEFAULT_USER_AGENT = "NoteMeld-WebNote/1.0"


def preview_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... <truncated {len(text) - limit} chars>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a URL and print response metadata/body preview."
    )
    parser.add_argument("url", help="Target URL to inspect")
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds (default: 15.0)",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=4000,
        help="Max body characters to print (default: 4000)",
    )
    parser.add_argument(
        "--save-body",
        type=Path,
        default=None,
        help="Optional file path to save the full response body",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        response = client.get(args.url, headers=headers)

    content_type = response.headers.get("content-type", "")
    body_text = response.text

    print(f"URL: {args.url}")
    print(f"Final URL: {response.url}")
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {content_type or '<missing>'}")
    print(f"Content-Length: {len(response.content)} bytes")
    print("Response Headers:")
    for key in sorted(response.headers):
        print(f"  {key}: {response.headers[key]}")

    if args.save_body:
        args.save_body.parent.mkdir(parents=True, exist_ok=True)
        args.save_body.write_text(body_text, encoding="utf-8")
        print(f"Saved body to: {args.save_body}")

    print("\nBody Preview:")
    print(preview_text(body_text, args.preview_chars))

    if "json" in content_type.lower():
        print("\nJSON Parsed Preview:")
        try:
            parsed = response.json()
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
            print(preview_text(formatted, args.preview_chars))
        except Exception as exc:
            print(f"JSON parse failed: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
