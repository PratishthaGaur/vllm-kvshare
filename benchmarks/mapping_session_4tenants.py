#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Create a 4-tenant session-level mapping for BurstGPT sessionized traces.

Tenant classes:
- interactive_chat: avg_input <= 512 and avg_output <= 256
- long_context: avg_input > 512 and avg_output <= 256
- long_generation: avg_input <= 512 and avg_output > 256
- mixed_heavy: avg_input > 512 and avg_output > 256
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 4-tenant session mapping for BurstGPT traces."
    )
    parser.add_argument(
        "--trace-path",
        type=str,
        required=True,
        help="Path to a sessionized BurstGPT CSV trace.",
    )
    parser.add_argument(
        "--output-mapping",
        type=str,
        required=True,
        help="Output JSON mapping file: session_id -> tenant_id",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=None,
        help="Optional output JSON report with class counts.",
    )
    parser.add_argument(
        "--interactive-max-input",
        type=int,
        default=512,
        help="Max avg input tokens for interactive_chat.",
    )
    parser.add_argument(
        "--interactive-max-output",
        type=int,
        default=256,
        help="Max avg output tokens for interactive_chat.",
    )
    return parser.parse_args()


def classify_session(
    avg_input_tokens: float,
    avg_output_tokens: float,
    interactive_max_input: int,
    interactive_max_output: int,
) -> str:
    if avg_input_tokens <= interactive_max_input and avg_output_tokens <= interactive_max_output:
        return "interactive_chat"
    if avg_input_tokens > interactive_max_input and avg_output_tokens <= interactive_max_output:
        return "long_context"
    if avg_input_tokens <= interactive_max_input and avg_output_tokens > interactive_max_output:
        return "long_generation"
    return "mixed_heavy"


def main() -> None:
    args = parse_args()
    trace_path = Path(args.trace_path)
    output_mapping = Path(args.output_mapping)
    output_report = Path(args.output_report) if args.output_report else None

    sessions: dict[str, dict[str, float]] = {}
    with trace_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            session_id = (row.get("Session ID") or "").strip()
            if not session_id:
                continue
            request_tokens = int(row["Request tokens"])
            response_tokens = int(row["Response tokens"])
            stats = sessions.get(session_id)
            if stats is None:
                stats = sessions[session_id] = {
                    "request_count": 0,
                    "input_sum": 0,
                    "output_sum": 0,
                }
            stats["request_count"] += 1
            stats["input_sum"] += request_tokens
            stats["output_sum"] += response_tokens

    mapping: dict[str, str] = {}
    class_session_counts: Counter[str] = Counter()
    class_request_counts: Counter[str] = Counter()

    for session_id, stats in sessions.items():
        avg_input = stats["input_sum"] / stats["request_count"]
        avg_output = stats["output_sum"] / stats["request_count"]
        tenant_id = classify_session(
            avg_input,
            avg_output,
            args.interactive_max_input,
            args.interactive_max_output,
        )
        mapping[session_id] = tenant_id
        class_session_counts[tenant_id] += 1
        class_request_counts[tenant_id] += int(stats["request_count"])

    output_mapping.parent.mkdir(parents=True, exist_ok=True)
    with output_mapping.open("w") as f:
        json.dump(mapping, f, indent=2, sort_keys=True)

    report = {
        "trace_path": str(trace_path),
        "num_sessions": len(mapping),
        "interactive_max_input": args.interactive_max_input,
        "interactive_max_output": args.interactive_max_output,
        "class_session_counts": dict(class_session_counts),
        "class_request_counts": dict(class_request_counts),
        "mapping_output": str(output_mapping),
    }

    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        with output_report.open("w") as f:
            json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
