#!/usr/bin/env python3
"""Micro-benchmark scaffold for Ask BPL orchestrator latency (TRD §12 smoke).

Runs from `packages/orchestrator` via `python -m ask_bpl_orchestrator.latency_report`.
"""

from __future__ import annotations

import argparse
import os
import time

import httpx


def _median_ms(samples: list[float]) -> float:
    if not samples:
        return -1.0
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid] * 1000
    return 0.5 * (ordered[mid - 1] + ordered[mid]) * 1000


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return -1.0
    size = len(sorted_samples)
    if size == 1:
        return sorted_samples[0] * 1000
    idx = pct / 100 * (size - 1)
    lower = int(idx)
    upper = min(lower + 1, size - 1)
    weight = idx - lower
    return (sorted_samples[lower] * (1 - weight) + sorted_samples[upper] * weight) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask BPL latency sampler")
    parser.add_argument("--base", default=os.environ.get("ASKBPL_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument(
        "--skip-ask",
        action="store_true",
        help="Only measure `/healthz` (no bearer token issuance).",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("ASKBPL_TEST_EMAIL", "pilot-demo@bklynlibrary.org"),
    )
    parser.add_argument("--code", default=os.environ.get("ASKBPL_TEST_CODE", "DEMO2026"))
    args = parser.parse_args()

    health_samples: list[float] = []
    auth_samples: list[float] = []
    ask_samples: list[float] = []

    with httpx.Client(base_url=args.base.rstrip("/"), timeout=120.0) as client:
        for _index in range(args.iterations):
            start = time.perf_counter()
            response = client.get("/healthz")
            elapsed = time.perf_counter() - start
            response.raise_for_status()
            health_samples.append(elapsed)

        if args.skip_ask:
            health_sorted = sorted(health_samples)
            print("Skipping auth/ask timings (--skip-ask).")  # noqa: T201
            print(f"healthz_med_ms {_median_ms(health_samples):.2f}")  # noqa: T201
            print(f"healthz_p95_ms {_percentile(health_sorted, 95):.2f}")  # noqa: T201
            return

        bearer_token = ""
        for _index in range(args.iterations):
            payload = {
                "email": args.email,
                "access_code": args.code,
                "attribution_mode": "attributed",
            }
            start = time.perf_counter()
            sign = client.post("/auth/sign-in", json=payload)
            elapsed_sign = time.perf_counter() - start
            sign.raise_for_status()
            auth_samples.append(elapsed_sign)
            bearer_token = str(sign.json()["token"])

        headers = {"Authorization": f"Bearer {bearer_token}"}

        ask_body = {"question": "What is covered by the fundraising policy timelines?"}

        for _index in range(args.iterations):
            started = time.perf_counter()
            ask_response = client.post("/questions/ask", headers=headers, json=ask_body)
            latency = time.perf_counter() - started
            ask_response.raise_for_status()
            ask_samples.append(latency)

    print("latency_report")  # noqa: T201
    print(f"healthz_med_ms {_median_ms(health_samples):.2f}")  # noqa: T201
    print(f"sign_in_med_ms {_median_ms(auth_samples):.2f}")  # noqa: T201
    print(f"ask_med_ms {_median_ms(ask_samples):.2f}")  # noqa: T201
    sorted_ask = sorted(ask_samples)
    print(f"ask_p95_ms {_percentile(sorted_ask, 95):.2f}")  # noqa: T201


if __name__ == "__main__":
    main()
