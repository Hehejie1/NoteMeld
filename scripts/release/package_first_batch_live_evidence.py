#!/usr/bin/env python3
"""Validate and package the 19 bound live-gate files for stable promotion."""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

from verify_first_batch_ledger import LedgerError, parse_ledger, verify_ledger


class PackageError(RuntimeError):
    pass


def package_evidence(ledger: Path, output: Path, version: str, commit: str) -> dict[str, object]:
    if output.exists():
        raise PackageError("evidence bundle output already exists")
    source = ledger.read_text(encoding="utf-8")
    approval = verify_ledger(
        source,
        evidence_root=ledger.parent,
        expected_version=version,
        expected_commit=commit.lower(),
    )
    rows = parse_ledger(source)
    entries: list[tuple[Path, str]] = [(ledger, "ledger.md")]
    for gate_id, (_status, reference) in sorted(rows.items()):
        entries.append(((ledger.parent / reference).resolve(), reference))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, path.read_bytes())
    return {
        "output": str(output),
        "gate_count": approval["passed"],
        "file_count": len(entries),
        "version": version,
        "commit": commit.lower(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        result = package_evidence(args.ledger, args.output, args.expected_version, args.expected_commit)
    except (OSError, LedgerError, PackageError, ValueError) as exc:
        parser.error(str(exc))
    print(f"packaged {result['gate_count']} live gates into {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
