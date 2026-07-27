#!/usr/bin/env python3
"""Generate Tauri updater latest.json manifest."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    if len(sys.argv) < 4:
        print("Usage: generate-latest-json.py <stage_dir> <version> <base_url>")
        sys.exit(1)

    stage_dir = Path(sys.argv[1])
    version = sys.argv[2]
    base_url = sys.argv[3].rstrip("/")

    def read_signature(path: Path) -> str:
        text = path.read_text(encoding="utf-8").strip()
        if "Public signature:" not in text:
            return text
        return text.split("Public signature:", 1)[1].strip().splitlines()[0].strip()

    def platform_key(path: Path) -> str | None:
        name = path.name.lower()
        if name.endswith(".app.tar.gz"):
            if "aarch64" in name or "arm64" in name:
                return "darwin-aarch64"
            if "x64" in name or "x86_64" in name:
                return "darwin-x86_64"
            return "darwin-aarch64"
        if name.endswith(".msi.zip"):
            return "windows-x86_64"
        if name.endswith(".appimage.tar.gz"):
            return "linux-x86_64"
        return None

    platforms = {}
    for artifact in sorted(stage_dir.iterdir()):
        key = platform_key(artifact)
        if not key:
            continue

        signature_path = artifact.with_name(f"{artifact.name}.sig")
        if not signature_path.exists():
            print(f"Warning: missing signature for {artifact.name}, skipping", file=sys.stderr)
            continue

        platforms[key] = {
            "signature": read_signature(signature_path),
            "url": f"{base_url}/{artifact.name}",
        }

    if not platforms:
        print(f"Error: no updater artifacts found in {stage_dir}", file=sys.stderr)
        sys.exit(1)

    latest = {
        "version": version,
        "notes": "NoteMeld desktop update. User data stays in the application data directory.",
        "pub_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platforms": platforms,
    }

    (stage_dir / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {stage_dir / 'latest.json'}")
    print(f"Platforms: {', '.join(platforms.keys())}")


if __name__ == "__main__":
    main()
