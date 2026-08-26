"""Build the deterministic local Release fixture for official.link-note."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = [ROOT / "README.md", ROOT / "src" / "official_link_note.py"]
MANIFEST = ROOT / "manifest.json"
INDEX = ROOT / "package-index.json"
RELEASE = ROOT / "release-fixture"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    files = []
    for path in PAYLOADS:
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": digest(path),
            "media_type": "text/plain",
            "entrypoint": path.name == "official_link_note.py",
        })
    package_digest = "sha256:" + hashlib.sha256(
        "".join(f"{item['path']}\0{item['sha256']}\n" for item in files).encode()
    ).hexdigest()
    index = {"index_version": 1, "files": files, "package_digest": package_digest}
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    manifest = json.loads(MANIFEST.read_text())
    manifest["package"] = index
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    RELEASE.mkdir(exist_ok=True)
    archive = RELEASE / "official-link-note-1.0.0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in [MANIFEST, INDEX, *PAYLOADS]:
            name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, path.read_bytes())
    (RELEASE / "release.json").write_text(json.dumps({
        "repository": "local://notemeld/official-link-note",
        "tag": "v1.0.0",
        "artifact": archive.name,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
