#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Generate tenant mappings for BurstGPT traces and recommend contention windows.

Heuristic tenant split:
- tenant_a: short, conversation-style, latency-sensitive requests
- tenant_b: everything else, including KV-heavy and background requests

This is designed for noisy-neighbor experiments where tenant_b should create
KV cache pressure and scheduler contention against tenant_a.
"""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class WindowStats:
    start: int
    end: int
    score: float
    tenant_a_requests: int
    tenant_b_requests: int
    tenant_b_heavy_requests: int
    tenant_a_tokens: int
    tenant_b_tokens: int
    conversation_requests: int
    api_requests: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build tenant mapping and recommended windows for BurstGPT traces."
    )
    parser.add_argument(
        "--trace-path",
        type=str,
        required=True,
        help="Path to BurstGPT CSV trace file.",
    )
    parser.add_argument(
        "--output-mapping",
        type=str,
        required=True,
        help="Path to write session_id -> tenant_id JSON mapping.",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=None,
        help="Optional path to write analysis report JSON.",
    )
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=900,
        help="Window size for contention analysis. Default: 900 (15 min).",
    )
    parser.add_argument(
        "--tenant-a-max-input",
        type=int,
        default=512,
        help="Max input tokens for tenant_a requests.",
    )
    parser.add_argument(
        "--tenant-a-max-output",
        type=int,
        default=256,
        help="Max output tokens for tenant_a requests.",
    )
    parser.add_argument(
        "--tenant-b-heavy-input",
        type=int,
        default=1024,
        help="Input token threshold for KV-heavy tenant_b requests.",
    )
    parser.add_argument(
        "--tenant-b-heavy-output",
        type=int,
        default=512,
        help="Output token threshold for KV-heavy tenant_b requests.",
    )
    parser.add_argument(
        "--top-k-windows",
        type=int,
        default=10,
        help="Number of recommended windows to include in the report.",
    )
    return parser.parse_args()


def resolve_session_id(row: dict[str, str], row_index: int) -> str:
    return (row.get("Session ID") or "").strip() or f"__row_{row_index}"


def is_tenant_a(
    row: dict[str, str],
    tenant_a_max_input: int,
    tenant_a_max_output: int,
) -> bool:
    log_type = (row.get("Log Type") or "").strip()
    request_tokens = int(row["Request tokens"])
    response_tokens = int(row["Response tokens"])
    return (
        log_type == "Conversation log"
        and request_tokens <= tenant_a_max_input
        and response_tokens <= tenant_a_max_output
    )


def is_tenant_b_heavy(
    row: dict[str, str],
    tenant_b_heavy_input: int,
    tenant_b_heavy_output: int,
) -> bool:
    request_tokens = int(row["Request tokens"])
    response_tokens = int(row["Response tokens"])
    return (
        request_tokens >= tenant_b_heavy_input
        or response_tokens >= tenant_b_heavy_output
    )


def main() -> None:
    args = parse_args()
    trace_path = Path(args.trace_path)
    output_mapping = Path(args.output_mapping)
    output_report = Path(args.output_report) if args.output_report else None

    mapping: dict[str, str] = {}
    windows: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "tenant_a_requests": 0,
            "tenant_b_requests": 0,
            "tenant_b_heavy_requests": 0,
            "tenant_a_tokens": 0,
            "tenant_b_tokens": 0,
            "conversation_requests": 0,
            "api_requests": 0,
        }
    )

    total_requests = 0
    min_timestamp = None
    max_timestamp = None

    with trace_path.open() as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader):
            total_requests += 1
            session_id = resolve_session_id(row, row_index)
            timestamp = int(float(row["Timestamp"]))
            request_tokens = int(row["Request tokens"])
            response_tokens = int(row["Response tokens"])
            total_tokens = request_tokens + response_tokens
            bucket_start = (timestamp // args.window_seconds) * args.window_seconds

            if min_timestamp is None or timestamp < min_timestamp:
                min_timestamp = timestamp
            if max_timestamp is None or timestamp > max_timestamp:
                max_timestamp = timestamp

            tenant_id = (
                "tenant_a"
                if is_tenant_a(
                    row,
                    args.tenant_a_max_input,
                    args.tenant_a_max_output,
                )
                else "tenant_b"
            )
            mapping[session_id] = tenant_id

            window = windows[bucket_start]
            if (row.get("Log Type") or "").strip() == "Conversation log":
                window["conversation_requests"] += 1
            else:
                window["api_requests"] += 1

            if tenant_id == "tenant_a":
                window["tenant_a_requests"] += 1
                window["tenant_a_tokens"] += total_tokens
            else:
                window["tenant_b_requests"] += 1
                window["tenant_b_tokens"] += total_tokens
                if is_tenant_b_heavy(
                    row,
                    args.tenant_b_heavy_input,
                    args.tenant_b_heavy_output,
                ):
                    window["tenant_b_heavy_requests"] += 1

    scored_windows: list[WindowStats] = []
    for start, window in windows.items():
        if window["tenant_a_requests"] == 0 or window["tenant_b_requests"] == 0:
            continue

        # Prefer windows with:
        # - enough tenant_a requests to expose foreground impact
        # - lots of tenant_b background pressure
        # - many KV-heavy tenant_b requests
        score = (
            min(window["tenant_a_requests"], 500) * 2
            + min(window["tenant_b_requests"], 4000)
            + window["tenant_b_tokens"] / 800
            + window["tenant_b_heavy_requests"] * 8
        )
        scored_windows.append(
            WindowStats(
                start=start,
                end=start + args.window_seconds,
                score=score,
                tenant_a_requests=window["tenant_a_requests"],
                tenant_b_requests=window["tenant_b_requests"],
                tenant_b_heavy_requests=window["tenant_b_heavy_requests"],
                tenant_a_tokens=window["tenant_a_tokens"],
                tenant_b_tokens=window["tenant_b_tokens"],
                conversation_requests=window["conversation_requests"],
                api_requests=window["api_requests"],
            )
        )

    scored_windows.sort(key=lambda w: w.score, reverse=True)
    recommended = [asdict(window) for window in scored_windows[: args.top_k_windows]]

    output_mapping.parent.mkdir(parents=True, exist_ok=True)
    with output_mapping.open("w") as f:
        json.dump(mapping, f, indent=2, sort_keys=True)

    report = {
        "trace_path": str(trace_path),
        "total_requests": total_requests,
        "unique_sessions": len(mapping),
        "timestamp_start": min_timestamp,
        "timestamp_end": max_timestamp,
        "span_seconds": (
            None if min_timestamp is None or max_timestamp is None
            else max_timestamp - min_timestamp
        ),
        "heuristic": {
            "tenant_a": {
                "log_type": "Conversation log",
                "max_input_tokens": args.tenant_a_max_input,
                "max_output_tokens": args.tenant_a_max_output,
            },
            "tenant_b": {
                "description": "All other requests",
                "heavy_input_tokens": args.tenant_b_heavy_input,
                "heavy_output_tokens": args.tenant_b_heavy_output,
            },
        },
        "recommended_windows": recommended,
        "recommended_primary_window": recommended[0] if recommended else None,
        "mapping_output": str(output_mapping),
    }

    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        with output_report.open("w") as f:
            json.dump(report, f, indent=2)

    tenant_a_count = sum(1 for tenant in mapping.values() if tenant == "tenant_a")
    tenant_b_count = sum(1 for tenant in mapping.values() if tenant == "tenant_b")
    print(f"Trace: {trace_path}")
    print(f"Requests/session ids mapped: {len(mapping)}")
    print(f"tenant_a assignments: {tenant_a_count}")
    print(f"tenant_b assignments: {tenant_b_count}")
    print(f"Mapping written to: {output_mapping}")
    if output_report:
        print(f"Report written to: {output_report}")
    if report["recommended_primary_window"]:
        best = report["recommended_primary_window"]
        print(
            "Recommended window:",
            f"{best['start']} -> {best['end']}",
            f"(tenant_a={best['tenant_a_requests']}, "
            f"tenant_b={best['tenant_b_requests']}, "
            f"tenant_b_heavy={best['tenant_b_heavy_requests']})",
        )


if __name__ == "__main__":
    main()
