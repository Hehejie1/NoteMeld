#!/usr/bin/env python3
"""Measure bounded local API latency for the new-product release gate.

The script intentionally measures read-only endpoints only. It does not create
or mutate user data, and it emits JSON so CI or a release checklist can retain
the exact environment and samples used for a baseline.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


DEFAULT_ENDPOINTS = (
    "/api/mobile/projection?workspace_id=default",
    "/api/applications",
    "/api/monitoring/snapshot?days=1",
)


def _request(url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = int(response.status)
    except urllib.error.HTTPError as error:
        error.read()
        status = int(error.code)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, elapsed_ms


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return round(ordered[index], 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8483")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    results: list[dict[str, Any]] = []
    for path in DEFAULT_ENDPOINTS:
        samples: list[float] = []
        statuses: list[int] = []
        for _ in range(args.iterations):
            status, elapsed_ms = _request(args.base_url.rstrip("/") + path, args.timeout)
            statuses.append(status)
            samples.append(elapsed_ms)
        results.append(
            {
                "path": path,
                "statuses": statuses,
                "success_rate": round(sum(status < 400 for status in statuses) / len(statuses), 3),
                "samples_ms": [round(value, 2) for value in samples],
                "p50_ms": _percentile(samples, 0.50),
                "p95_ms": _percentile(samples, 0.95),
                "max_ms": round(max(samples), 2),
            }
        )

    payload = {
        "schema_version": "notemeld.perf-baseline.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "iterations": args.iterations,
        "timeout_seconds": args.timeout,
        "host": {"platform": platform.platform(), "python": platform.python_version()},
        "endpoints": results,
        "aggregate": {
            "p50_ms": round(statistics.median(item["p50_ms"] for item in results), 2),
            "p95_ms": round(max(item["p95_ms"] for item in results), 2),
            "all_requests_succeeded": all(item["success_rate"] == 1 for item in results),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["aggregate"]["all_requests_succeeded"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
