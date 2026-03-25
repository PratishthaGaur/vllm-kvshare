#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
Analysis script for BurstGPT trace replay results.

Helps analyze and compare benchmark results from multiple runs.

Usage:
    python benchmarks/analyze_burstgpt_results.py \
        --results-dir results/burstgpt_baseline \
        --output-format table

    python benchmarks/analyze_burstgpt_results.py \
        --compare results/burstgpt_baseline results/burstgpt_with_caching \
        --output-format csv
"""

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np


@dataclass
class BenchmarkStats:
    """Computed statistics from benchmark results."""
    name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float

    # Latency stats
    latency_mean: float
    latency_median: float
    latency_p95: float
    latency_p99: float
    latency_min: float
    latency_max: float

    # TTFT stats
    ttft_mean: float
    ttft_median: float
    ttft_p95: float
    ttft_p99: float

    # Token stats
    total_input_tokens: int
    total_output_tokens: int
    input_tokens_per_sec: float
    output_tokens_per_sec: float

    # Throughput
    total_time: float
    requests_per_sec: float


def load_benchmark_results(results_dir: Path) -> dict:
    """Load results.json from a benchmark directory."""
    results_file = results_dir / "results.json"
    if not results_file.exists():
        raise FileNotFoundError(f"Results file not found: {results_file}")

    with open(results_file, 'r') as f:
        return json.load(f)


def compute_stats(results: dict) -> BenchmarkStats:
    """Compute statistics from benchmark results."""
    metrics = results["metrics"]
    successful = [m for m in metrics if m["error"] is None]
    failed = [m for m in metrics if m["error"] is not None]

    name = results.get("benchmark_config", {}).get("model", "Unknown")

    if successful:
        latencies = [m["total_latency"] for m in successful]
        ttft_times = [m["time_to_first_token"] for m in successful]

        latency_mean = statistics.mean(latencies)
        latency_median = statistics.median(latencies)
        latency_p95 = np.percentile(latencies, 95)
        latency_p99 = np.percentile(latencies, 99)
        latency_min = min(latencies)
        latency_max = max(latencies)

        ttft_mean = statistics.mean(ttft_times)
        ttft_median = statistics.median(ttft_times)
        ttft_p95 = np.percentile(ttft_times, 95)
        ttft_p99 = np.percentile(ttft_times, 99)

        total_input = sum(m["actual_input_tokens"] for m in successful)
        total_output = sum(m["actual_output_tokens"] for m in successful)
    else:
        latency_mean = latency_median = latency_p95 = latency_p99 = 0
        latency_min = latency_max = 0
        ttft_mean = ttft_median = ttft_p95 = ttft_p99 = 0
        total_input = total_output = 0

    total_time = max(m["timestamp"] for m in successful) - min(m["timestamp"] for m in successful) if successful else 0
    total_time = max(total_time, 1)  # Avoid division by zero

    requests_per_sec = len(successful) / total_time if total_time > 0 else 0
    input_tokens_per_sec = total_input / total_time if total_time > 0 else 0
    output_tokens_per_sec = total_output / total_time if total_time > 0 else 0

    success_rate = len(successful) / len(metrics) if metrics else 0

    return BenchmarkStats(
        name=name,
        total_requests=len(metrics),
        successful_requests=len(successful),
        failed_requests=len(failed),
        success_rate=success_rate,
        latency_mean=latency_mean,
        latency_median=latency_median,
        latency_p95=latency_p95,
        latency_p99=latency_p99,
        latency_min=latency_min,
        latency_max=latency_max,
        ttft_mean=ttft_mean,
        ttft_median=ttft_median,
        ttft_p95=ttft_p95,
        ttft_p99=ttft_p99,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        input_tokens_per_sec=input_tokens_per_sec,
        output_tokens_per_sec=output_tokens_per_sec,
        total_time=total_time,
        requests_per_sec=requests_per_sec,
    )


def print_stats_table(stats_list: list[BenchmarkStats]):
    """Print statistics as a formatted table."""
    if not stats_list:
        print("No statistics to display")
        return

    # Header
    print("\n" + "="*120)
    print("BurstGPT Benchmark Results Summary")
    print("="*120)

    # Throughput section
    print("\n[THROUGHPUT]")
    print(f"{'Benchmark':<25} {'Requests/s':<15} {'Input Toks/s':<15} {'Output Toks/s':<15} {'Success Rate':<15}")
    print("-" * 85)
    for stats in stats_list:
        print(f"{stats.name:<25} {stats.requests_per_sec:<15.2f} {stats.input_tokens_per_sec:<15.2f} {stats.output_tokens_per_sec:<15.2f} {stats.success_rate*100:<14.1f}%")

    # Latency section
    print("\n[LATENCY - Total Response Time (seconds)]")
    print(f"{'Benchmark':<25} {'Mean':<12} {'Median':<12} {'P95':<12} {'P99':<12} {'Min':<12} {'Max':<12}")
    print("-" * 95)
    for stats in stats_list:
        print(f"{stats.name:<25} {stats.latency_mean:<12.3f} {stats.latency_median:<12.3f} {stats.latency_p95:<12.3f} {stats.latency_p99:<12.3f} {stats.latency_min:<12.3f} {stats.latency_max:<12.3f}")

    # Time-to-first-token section
    print("\n[TIME TO FIRST TOKEN - Prefill Latency (milliseconds)]")
    print(f"{'Benchmark':<25} {'Mean':<12} {'Median':<12} {'P95':<12} {'P99':<12}")
    print("-" * 65)
    for stats in stats_list:
        print(f"{stats.name:<25} {stats.ttft_mean*1000:<12.2f} {stats.ttft_median*1000:<12.2f} {stats.ttft_p95*1000:<12.2f} {stats.ttft_p99*1000:<12.2f}")

    # Token statistics
    print("\n[TOKEN STATISTICS]")
    print(f"{'Benchmark':<25} {'Total Input':<15} {'Total Output':<15} {'Requests':<15}")
    print("-" * 70)
    for stats in stats_list:
        print(f"{stats.name:<25} {stats.total_input_tokens:<15,d} {stats.total_output_tokens:<15,d} {stats.successful_requests:<15,d}")

    print("="*120 + "\n")


def print_stats_csv(stats_list: list[BenchmarkStats]):
    """Print statistics in CSV format."""
    if not stats_list:
        print("No statistics to display")
        return

    # CSV header
    headers = [
        "Benchmark", "Total Requests", "Successful", "Failed", "Success Rate (%)",
        "Latency Mean (s)", "Latency Median (s)", "Latency P95 (s)", "Latency P99 (s)",
        "TTFT Mean (ms)", "TTFT Median (ms)", "TTFT P95 (ms)", "TTFT P99 (ms)",
        "Total Input Tokens", "Total Output Tokens",
        "Input Tokens/sec", "Output Tokens/sec", "Requests/sec"
    ]
    print(",".join(headers))

    # CSV rows
    for stats in stats_list:
        row = [
            stats.name,
            stats.total_requests,
            stats.successful_requests,
            stats.failed_requests,
            stats.success_rate * 100,
            stats.latency_mean,
            stats.latency_median,
            stats.latency_p95,
            stats.latency_p99,
            stats.ttft_mean * 1000,
            stats.ttft_median * 1000,
            stats.ttft_p95 * 1000,
            stats.ttft_p99 * 1000,
            stats.total_input_tokens,
            stats.total_output_tokens,
            stats.input_tokens_per_sec,
            stats.output_tokens_per_sec,
            stats.requests_per_sec,
        ]
        print(",".join(str(x) for x in row))


def compute_speedup(baseline: BenchmarkStats, other: BenchmarkStats) -> dict:
    """Compute speedup factors compared to baseline."""
    return {
        "name": other.name,
        "latency_speedup": baseline.latency_mean / other.latency_mean if other.latency_mean > 0 else 0,
        "ttft_speedup": baseline.ttft_mean / other.ttft_mean if other.ttft_mean > 0 else 0,
        "throughput_speedup": other.requests_per_sec / baseline.requests_per_sec if baseline.requests_per_sec > 0 else 0,
        "output_tokens_speedup": other.output_tokens_per_sec / baseline.output_tokens_per_sec if baseline.output_tokens_per_sec > 0 else 0,
    }


def print_comparison(baseline_stats: BenchmarkStats, other_stats_list: list[BenchmarkStats]):
    """Print comparison against baseline."""
    print("\n" + "="*100)
    print(f"Comparison vs Baseline: {baseline_stats.name}")
    print("="*100)
    print(f"{'Benchmark':<25} {'Latency':<15} {'TTFT':<15} {'Throughput':<15} {'Output Tokens':<15}")
    print(f"{'(vs baseline)':<25} {'(lower=better)':<15} {'(lower=better)':<15} {'(higher=better)':<15} {'(higher=better)':<15}")
    print("-" * 90)

    for other_stats in other_stats_list:
        speedup = compute_speedup(baseline_stats, other_stats)
        print(f"{speedup['name']:<25} {speedup['latency_speedup']:<15.2f}x {speedup['ttft_speedup']:<15.2f}x {speedup['throughput_speedup']:<15.2f}x {speedup['output_tokens_speedup']:<15.2f}x")

    print("="*100 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze BurstGPT trace replay benchmark results"
    )

    parser.add_argument(
        "--results-dir",
        type=str,
        help="Directory containing benchmark results.json"
    )

    parser.add_argument(
        "--compare",
        nargs="+",
        type=str,
        help="Compare multiple benchmark directories"
    )

    parser.add_argument(
        "--output-format",
        choices=["table", "csv"],
        default="table",
        help="Output format"
    )

    args = parser.parse_args()

    results_dirs = []

    if args.results_dir:
        results_dirs.append(Path(args.results_dir))

    if args.compare:
        results_dirs.extend([Path(d) for d in args.compare])

    if not results_dirs:
        print("Error: Please specify --results-dir or --compare")
        parser.print_help()
        return

    # Load and compute statistics
    stats_list = []
    for results_dir in results_dirs:
        try:
            results = load_benchmark_results(results_dir)
            stats = compute_stats(results)
            stats.name = results_dir.name
            stats_list.append(stats)
        except Exception as e:
            print(f"Error loading results from {results_dir}: {e}")

    if not stats_list:
        print("No valid benchmark results found")
        return

    # Output results
    if args.output_format == "table":
        print_stats_table(stats_list)

        # If comparing multiple, show comparison
        if len(stats_list) > 1:
            print_comparison(stats_list[0], stats_list[1:])

    elif args.output_format == "csv":
        print_stats_csv(stats_list)


if __name__ == "__main__":
    main()
