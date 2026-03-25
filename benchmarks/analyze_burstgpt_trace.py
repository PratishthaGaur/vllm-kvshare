#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Analyze BurstGPT traces to understand request/session structure before
constructing tenant classes.
"""

import argparse
import csv
import json
import math
from array import array
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SessionStats:
    request_count: int = 0
    input_sum: int = 0
    output_sum: int = 0
    max_input: int = 0
    max_output: int = 0
    first_timestamp: float = 0.0
    last_timestamp: float = 0.0
    log_type_counts: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.log_type_counts is None:
            self.log_type_counts = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a BurstGPT CSV trace."
    )
    parser.add_argument(
        "--trace-path",
        type=str,
        required=True,
        help="Path to BurstGPT CSV file.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional path to save full analysis JSON.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top sessions/windows to print.",
    )
    return parser.parse_args()


def percentile_from_sorted(values: array, q: float) -> float:
    if not values:
        return 0.0
    idx = (len(values) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return float(values[lo])
    frac = idx - lo
    return float(values[lo] * (1 - frac) + values[hi] * frac)


def summarize_numeric(values: array) -> dict[str, float]:
    sorted_values = array(values.typecode, values)
    sorted_values = array(values.typecode, sorted(sorted_values))
    total = sum(sorted_values)
    count = len(sorted_values)
    mean = total / count if count else 0.0
    var = sum((x - mean) ** 2 for x in sorted_values) / count if count else 0.0
    return {
        "count": count,
        "min": float(sorted_values[0]) if count else 0.0,
        "mean": float(mean),
        "std": float(math.sqrt(var)),
        "p50": percentile_from_sorted(sorted_values, 0.50),
        "p90": percentile_from_sorted(sorted_values, 0.90),
        "p95": percentile_from_sorted(sorted_values, 0.95),
        "p99": percentile_from_sorted(sorted_values, 0.99),
        "max": float(sorted_values[-1]) if count else 0.0,
    }


def coarse_shape(request_tokens: int, response_tokens: int) -> str:
    if request_tokens <= 512 and response_tokens <= 256:
        return "short_in_short_out"
    if request_tokens > 512 and response_tokens <= 256:
        return "long_in_short_out"
    if request_tokens <= 512 and response_tokens > 256:
        return "short_in_long_out"
    return "long_in_long_out"


def session_summary(session: SessionStats, session_id: str) -> dict[str, object]:
    duration = max(0.0, session.last_timestamp - session.first_timestamp)
    return {
        "session_id": session_id,
        "request_count": session.request_count,
        "duration_seconds": duration,
        "avg_input_tokens": session.input_sum / session.request_count,
        "avg_output_tokens": session.output_sum / session.request_count,
        "max_input_tokens": session.max_input,
        "max_output_tokens": session.max_output,
        "total_tokens": session.input_sum + session.output_sum,
        "log_type_counts": session.log_type_counts,
    }


def main() -> None:
    args = parse_args()
    trace_path = Path(args.trace_path)

    input_tokens = array("I")
    output_tokens = array("I")
    total_tokens = array("I")

    per_minute_requests: dict[int, int] = defaultdict(int)
    per_minute_tokens: dict[int, int] = defaultdict(int)
    per_15min_requests: dict[int, int] = defaultdict(int)
    per_15min_tokens: dict[int, int] = defaultdict(int)

    identified_sessions: dict[str, SessionStats] = {}
    anonymous_shape_counts: Counter[str] = Counter()
    identified_shape_counts: Counter[str] = Counter()
    log_type_counts: Counter[str] = Counter()
    model_type_counts: Counter[str] = Counter()

    total_rows = 0
    anonymous_rows = 0
    min_timestamp: float | None = None
    max_timestamp: float | None = None

    with trace_path.open() as f:
        reader = csv.DictReader(f)
        for row_idx, row in enumerate(reader):
            total_rows += 1
            ts = float(row["Timestamp"])
            req = int(row["Request tokens"])
            resp = int(row["Response tokens"])
            log_type = (row.get("Log Type") or "").strip() or "UNKNOWN"
            model_type = (row.get("Model") or "").strip() or "UNKNOWN"
            session_id = (row.get("Session ID") or "").strip()

            if min_timestamp is None or ts < min_timestamp:
                min_timestamp = ts
            if max_timestamp is None or ts > max_timestamp:
                max_timestamp = ts

            input_tokens.append(req)
            output_tokens.append(resp)
            total_tokens.append(req + resp)

            minute_bucket = int(ts // 60)
            q15_bucket = int(ts // 900)
            per_minute_requests[minute_bucket] += 1
            per_minute_tokens[minute_bucket] += req + resp
            per_15min_requests[q15_bucket] += 1
            per_15min_tokens[q15_bucket] += req + resp

            log_type_counts[log_type] += 1
            model_type_counts[model_type] += 1

            shape = coarse_shape(req, resp)
            if session_id:
                identified_shape_counts[shape] += 1
                stats = identified_sessions.get(session_id)
                if stats is None:
                    stats = SessionStats(
                        request_count=0,
                        input_sum=0,
                        output_sum=0,
                        max_input=0,
                        max_output=0,
                        first_timestamp=ts,
                        last_timestamp=ts,
                    )
                    identified_sessions[session_id] = stats
                stats.request_count += 1
                stats.input_sum += req
                stats.output_sum += resp
                stats.max_input = max(stats.max_input, req)
                stats.max_output = max(stats.max_output, resp)
                stats.first_timestamp = min(stats.first_timestamp, ts)
                stats.last_timestamp = max(stats.last_timestamp, ts)
                stats.log_type_counts[log_type] = stats.log_type_counts.get(log_type, 0) + 1
            else:
                anonymous_rows += 1
                anonymous_shape_counts[shape] += 1

    session_request_counts = array("I")
    session_durations = array("f")
    session_avg_inputs = array("f")
    session_avg_outputs = array("f")
    multi_request_sessions = 0

    top_sessions_by_tokens: list[dict[str, object]] = []
    top_sessions_by_requests: list[dict[str, object]] = []
    for session_id, session in identified_sessions.items():
        session_request_counts.append(session.request_count)
        duration = max(0.0, session.last_timestamp - session.first_timestamp)
        session_durations.append(duration)
        session_avg_inputs.append(session.input_sum / session.request_count)
        session_avg_outputs.append(session.output_sum / session.request_count)
        if session.request_count > 1:
            multi_request_sessions += 1
        top_sessions_by_tokens.append(session_summary(session, session_id))
        top_sessions_by_requests.append(session_summary(session, session_id))

    top_sessions_by_tokens.sort(key=lambda s: s["total_tokens"], reverse=True)
    top_sessions_by_requests.sort(key=lambda s: s["request_count"], reverse=True)

    minute_request_values = array("I", per_minute_requests.values())
    minute_token_values = array("I", per_minute_tokens.values())
    q15_request_values = array("I", per_15min_requests.values())
    q15_token_values = array("I", per_15min_tokens.values())

    top_minutes = sorted(
        (
            {
                "minute_bucket": bucket,
                "requests": per_minute_requests[bucket],
                "tokens": per_minute_tokens[bucket],
            }
            for bucket in per_minute_requests
        ),
        key=lambda x: (x["requests"], x["tokens"]),
        reverse=True,
    )[: args.top_k]

    top_q15 = sorted(
        (
            {
                "window_start": bucket * 900,
                "window_end": bucket * 900 + 900,
                "requests": per_15min_requests[bucket],
                "tokens": per_15min_tokens[bucket],
            }
            for bucket in per_15min_requests
        ),
        key=lambda x: (x["requests"], x["tokens"]),
        reverse=True,
    )[: args.top_k]

    result = {
        "trace_path": str(trace_path),
        "overall": {
            "total_rows": total_rows,
            "identified_session_count": len(identified_sessions),
            "anonymous_rows": anonymous_rows,
            "identified_session_rows": total_rows - anonymous_rows,
            "multi_request_session_count": multi_request_sessions,
            "timestamp_start": min_timestamp,
            "timestamp_end": max_timestamp,
            "trace_span_seconds": (
                max_timestamp - min_timestamp if min_timestamp is not None and max_timestamp is not None else 0.0
            ),
            "log_type_counts": dict(log_type_counts),
            "model_type_counts": dict(model_type_counts),
        },
        "request_token_stats": {
            "input_tokens": summarize_numeric(input_tokens),
            "output_tokens": summarize_numeric(output_tokens),
            "total_tokens": summarize_numeric(total_tokens),
        },
        "request_rate_stats": {
            "per_minute_requests": summarize_numeric(minute_request_values),
            "per_minute_tokens": summarize_numeric(minute_token_values),
            "per_15min_requests": summarize_numeric(q15_request_values),
            "per_15min_tokens": summarize_numeric(q15_token_values),
            "top_minutes": top_minutes,
            "top_15min_windows": top_q15,
        },
        "session_stats_identified_only": {
            "request_count_per_session": summarize_numeric(session_request_counts),
            "duration_seconds_per_session": summarize_numeric(session_durations),
            "avg_input_tokens_per_session": summarize_numeric(session_avg_inputs),
            "avg_output_tokens_per_session": summarize_numeric(session_avg_outputs),
            "top_sessions_by_total_tokens": top_sessions_by_tokens[: args.top_k],
            "top_sessions_by_request_count": top_sessions_by_requests[: args.top_k],
        },
        "coarse_request_shapes": {
            "identified_session_rows": dict(identified_shape_counts),
            "anonymous_rows": dict(anonymous_shape_counts),
        },
    }

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
