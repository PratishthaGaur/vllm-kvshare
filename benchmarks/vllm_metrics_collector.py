#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
vLLM Metrics Collector

Collects detailed vLLM server metrics including:
- KV cache pressure and recomputation
- Scheduling delays and preemption
- Cache hit rates
- Engine utilization

These metrics are fetched from vLLM's /metrics Prometheus endpoint.
"""

import asyncio
import re
import time
from dataclasses import dataclass, asdict
from typing import Optional

import aiohttp


@dataclass
class VLLMMetricsSnapshot:
    """Snapshot of vLLM metrics at a point in time."""
    timestamp: float

    # KV Cache Metrics
    kv_cache_usage_pct: Optional[float] = None  # 0-100%
    kv_cache_total_blocks: Optional[int] = None
    kv_cache_used_blocks: Optional[int] = None
    kv_cache_free_blocks: Optional[int] = None

    # Request Queue Metrics
    num_requests_running: Optional[int] = None
    num_requests_waiting: Optional[int] = None
    num_requests_swapped: Optional[int] = None

    # Token Metrics
    total_tokens_generated: Optional[int] = None
    total_input_tokens: Optional[int] = None

    # Preemption Metrics
    num_preemptions: Optional[int] = None
    num_context_swap_out: Optional[int] = None
    num_context_swap_in: Optional[int] = None

    # Iteration Metrics
    avg_iteration_latency_ms: Optional[float] = None
    iteration_bucket_1_token: Optional[int] = None
    iteration_bucket_8_tokens: Optional[int] = None
    iteration_bucket_16_tokens: Optional[int] = None
    iteration_bucket_32_tokens: Optional[int] = None
    iteration_bucket_64_tokens: Optional[int] = None
    iteration_bucket_128_tokens: Optional[int] = None

    # Engine Metrics
    engine_cache_usage_pct: Optional[float] = None
    engine_running_requests: Optional[int] = None


@dataclass
class RequestVLLMMetrics:
    """vLLM metrics associated with a single request."""
    request_id: int

    # Snapshot before request
    metrics_before: Optional[VLLMMetricsSnapshot] = None

    # Snapshot after request
    metrics_after: Optional[VLLMMetricsSnapshot] = None

    # Calculated deltas
    kv_cache_delta_blocks: Optional[int] = None  # Change in used blocks
    scheduling_delay_ms: Optional[float] = None  # Time waiting in queue
    preemptions_during_request: Optional[int] = None
    tokens_generated_during_request: Optional[int] = None

    # Additional vLLM-specific timing
    scheduler_wait_time_ms: Optional[float] = None

    def calculate_deltas(self):
        """Calculate delta metrics between snapshots."""
        if not self.metrics_before or not self.metrics_after:
            return

        # KV cache delta
        if (self.metrics_before.kv_cache_used_blocks is not None and
            self.metrics_after.kv_cache_used_blocks is not None):
            self.kv_cache_delta_blocks = (
                self.metrics_after.kv_cache_used_blocks -
                self.metrics_before.kv_cache_used_blocks
            )

        # Preemptions during request
        if (self.metrics_before.num_preemptions is not None and
            self.metrics_after.num_preemptions is not None):
            self.preemptions_during_request = (
                self.metrics_after.num_preemptions -
                self.metrics_before.num_preemptions
            )

        # Tokens generated during request
        if (self.metrics_before.total_tokens_generated is not None and
            self.metrics_after.total_tokens_generated is not None):
            self.tokens_generated_during_request = (
                self.metrics_after.total_tokens_generated -
                self.metrics_before.total_tokens_generated
            )

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'request_id': self.request_id,
            'kv_cache_delta_blocks': self.kv_cache_delta_blocks,
            'scheduling_delay_ms': self.scheduling_delay_ms,
            'preemptions_during_request': self.preemptions_during_request,
            'tokens_generated_during_request': self.tokens_generated_during_request,
            'scheduler_wait_time_ms': self.scheduler_wait_time_ms,
            'metrics_before': asdict(self.metrics_before) if self.metrics_before else None,
            'metrics_after': asdict(self.metrics_after) if self.metrics_after else None,
        }


class VLLMMetricsCollector:
    """Collects metrics from vLLM server's /metrics endpoint."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize metrics collector.

        Args:
            base_url: vLLM server base URL
        """
        self.base_url = base_url
        self.metrics_url = f"{base_url}/metrics"
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize aiohttp session."""
        self.session = aiohttp.ClientSession()

    async def shutdown(self):
        """Cleanup session."""
        if self.session:
            await self.session.close()

    async def fetch_metrics(self) -> Optional[VLLMMetricsSnapshot]:
        """
        Fetch current metrics from vLLM server.

        Returns:
            VLLMMetricsSnapshot with current metrics, or None if fetch failed
        """
        if not self.session:
            return None

        try:
            async with self.session.get(
                self.metrics_url,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return None

                content = await resp.text()
                return self._parse_prometheus_metrics(content)

        except Exception as e:
            print(f"Error fetching metrics: {e}")
            return None

    def _parse_prometheus_metrics(self, content: str) -> VLLMMetricsSnapshot:
        """Parse Prometheus metrics format."""
        snapshot = VLLMMetricsSnapshot(timestamp=time.time())

        lines = content.split('\n')

        for line in lines:
            if line.startswith('#') or not line.strip():
                continue

            # Parse metric line: metric_name{labels} value
            # Example: vllm:gpu_cache_usage_perc{model_name="..."} 75.5

            if 'gpu_cache_usage_perc' in line:
                snapshot.kv_cache_usage_pct = self._extract_value(line)

            elif 'kv_cache_usage_pct' in line or 'cache_usage_perc' in line:
                snapshot.kv_cache_usage_pct = self._extract_value(line)

            elif 'num_preemptions_total' in line:
                snapshot.num_preemptions = int(self._extract_value(line) or 0)

            elif 'context_swap_out_total' in line:
                snapshot.num_context_swap_out = int(self._extract_value(line) or 0)

            elif 'context_swap_in_total' in line:
                snapshot.num_context_swap_in = int(self._extract_value(line) or 0)

            elif 'tokens_generated_total' in line:
                snapshot.total_tokens_generated = int(self._extract_value(line) or 0)

            elif 'input_tokens_total' in line and 'vllm:input_tokens_total' in line:
                snapshot.total_input_tokens = int(self._extract_value(line) or 0)

            elif 'num_requests_running' in line:
                snapshot.num_requests_running = int(self._extract_value(line) or 0)

            elif 'num_requests_waiting' in line:
                snapshot.num_requests_waiting = int(self._extract_value(line) or 0)

            elif 'num_requests_swapped' in line:
                snapshot.num_requests_swapped = int(self._extract_value(line) or 0)

            elif 'iteration_tokens_total_sum' in line:
                # This is the sum of all tokens per iteration
                val = self._extract_value(line)
                if val:
                    snapshot.avg_iteration_latency_ms = val

        return snapshot

    def _extract_value(self, line: str) -> Optional[float]:
        """Extract numeric value from Prometheus metric line."""
        try:
            # Format: metric_name{...} value
            parts = line.rsplit(' ', 1)
            if len(parts) == 2:
                value_str = parts[1].strip()
                if value_str not in ('NaN', 'Inf', '+Inf', '-Inf'):
                    return float(value_str)
        except (ValueError, IndexError):
            pass

        return None


class RequestMetricsWithVLLM:
    """Extended request metrics including vLLM data."""

    def __init__(self, request_id: int):
        self.request_id = request_id
        self.request_start_time: Optional[float] = None
        self.response_end_time: Optional[float] = None
        self.queue_wait_start: Optional[float] = None
        self.execution_start: Optional[float] = None

        self.vllm_metrics_before: Optional[VLLMMetricsSnapshot] = None
        self.vllm_metrics_after: Optional[VLLMMetricsSnapshot] = None

        # Calculated metrics
        self.total_latency: Optional[float] = None
        self.time_to_first_token: Optional[float] = None
        self.scheduling_delay: Optional[float] = None
        self.actual_execution_time: Optional[float] = None
        self.kv_cache_delta: Optional[int] = None
        self.preemptions: Optional[int] = None

    def calculate_metrics(self):
        """Calculate all metrics."""
        if self.request_start_time and self.response_end_time:
            self.total_latency = self.response_end_time - self.request_start_time

        if self.queue_wait_start and self.execution_start:
            self.scheduling_delay = self.execution_start - self.queue_wait_start

        if self.execution_start and self.response_end_time:
            self.actual_execution_time = self.response_end_time - self.execution_start

        if self.vllm_metrics_before and self.vllm_metrics_after:
            if (self.vllm_metrics_before.kv_cache_used_blocks is not None and
                self.vllm_metrics_after.kv_cache_used_blocks is not None):
                self.kv_cache_delta = (
                    self.vllm_metrics_after.kv_cache_used_blocks -
                    self.vllm_metrics_before.kv_cache_used_blocks
                )

            if (self.vllm_metrics_before.num_preemptions is not None and
                self.vllm_metrics_after.num_preemptions is not None):
                self.preemptions = (
                    self.vllm_metrics_after.num_preemptions -
                    self.vllm_metrics_before.num_preemptions
                )

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'request_id': self.request_id,
            'total_latency': self.total_latency,
            'time_to_first_token': self.time_to_first_token,
            'scheduling_delay': self.scheduling_delay,
            'actual_execution_time': self.actual_execution_time,
            'kv_cache_delta_blocks': self.kv_cache_delta,
            'num_preemptions': self.preemptions,
            'vllm_metrics_before': asdict(self.vllm_metrics_before) if self.vllm_metrics_before else None,
            'vllm_metrics_after': asdict(self.vllm_metrics_after) if self.vllm_metrics_after else None,
        }


async def example_usage():
    """Example usage of the metrics collector."""
    collector = VLLMMetricsCollector("http://localhost:8000")
    await collector.initialize()

    try:
        # Fetch initial metrics
        metrics = await collector.fetch_metrics()
        if metrics:
            print(f"KV Cache Usage: {metrics.kv_cache_usage_pct}%")
            print(f"Requests Running: {metrics.num_requests_running}")
            print(f"Total Preemptions: {metrics.num_preemptions}")
    finally:
        await collector.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
