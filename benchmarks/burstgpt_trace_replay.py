#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
r"""
BurstGPT Trace Replay Benchmark for vLLM

Replays the BurstGPT trace against a vLLM server while maintaining:
- Exact inter-arrival times from the trace
- Matching input/output token counts
- Configurable model and vLLM settings (prefix caching, etc.)

Usage:
    # Start vLLM server first:
    vllm serve meta-llama/Llama-2-7b-hf \
        --enable-prefix-caching \
        --gpu-memory-utilization 0.9

    # Run the benchmark:
    python benchmarks/burstgpt_trace_replay.py \
        --trace-path data/BurstGPT/data/BurstGPT_1.csv \
        --base-url http://localhost:8000 \
        --model llama-2-7b-hf \
        --output-dir results/burstgpt_replay \
        --scale 1.0
"""

import argparse
import asyncio
import csv
import json
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiohttp
import numpy as np
from tqdm.asyncio import tqdm

from vllm_metrics_collector import VLLMMetricsCollector


@dataclass
class TraceRequest:
    """Represents a single request from the BurstGPT trace."""
    timestamp: float  # Arrival time in seconds
    session_id: str
    tenant_id: str
    request_tokens: int
    response_tokens: int
    model_type: str  # ChatGPT or GPT-4
    log_type: str


@dataclass
class RequestMetrics:
    """Metrics collected for a single request."""
    request_id: int
    timestamp: float  # Scheduled timestamp from trace
    request_tokens: int
    expected_output_tokens: int
    actual_input_tokens: int
    actual_output_tokens: int
    time_to_first_token: float
    total_latency: float
    session_id: str
    tenant_id: str
    log_type: str
    request_start_time: float = 0.0
    request_end_time: float = 0.0
    estimated_prefill_kv_tokens: int = 0
    estimated_peak_kv_tokens: int = 0
    estimated_prefill_kv_blocks: int = 0
    estimated_peak_kv_blocks: int = 0
    estimated_kv_footprint_share: float = 0.0
    cache_pressure_harmed: bool = False
    cache_pressure_harm_reasons: list[str] = None
    overlapping_swap_events: int = 0
    overlapping_preemption_events: int = 0
    overlapping_context_swap_out_events: int = 0
    overlapping_context_swap_in_events: int = 0
    approximate_recompute_events: int = 0
    approximate_recompute_cost_tokens: int = 0
    vllm_metrics_before: Optional[dict[str, Any]] = None
    vllm_metrics_after: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class SessionState:
    """Synthetic conversation state for a single BurstGPT session."""
    transcript: str = ""
    synthetic_turn_index: int = 0


@dataclass
class SampledVLLMMetrics:
    """Time-series sample of global vLLM metrics."""
    timestamp: float
    metrics: dict[str, Any]


class BurstGPTTraceReader:
    """Reads and parses BurstGPT trace CSV files."""

    def __init__(
        self,
        trace_path: str,
        scale: float = 1.0,
        max_duration_seconds: Optional[float] = None,
        start_timestamp: Optional[float] = None,
        end_timestamp: Optional[float] = None,
        tenant_assignments: Optional[dict[str, str]] = None,
        default_tenant: str = "unassigned",
        include_tenants: Optional[set[str]] = None,
    ):
        """
        Initialize trace reader.

        Args:
            trace_path: Path to BurstGPT CSV file
            scale: Scale factor for timestamps (e.g., 10.0 = 10x faster)
            max_duration_seconds: Maximum duration to include from trace (e.g., 900 for 15 min)
        """
        self.trace_path = Path(trace_path)
        self.scale = scale
        self.max_duration_seconds = max_duration_seconds
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp
        self.tenant_assignments = tenant_assignments or {}
        self.default_tenant = default_tenant
        self.include_tenants = include_tenants
        self.requests = []
        self._load_trace()

    def _load_trace(self):
        """Load and parse the CSV trace file."""
        first_selected_timestamp = None
        with open(self.trace_path, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                raw_timestamp = float(row['Timestamp'])

                if self.start_timestamp is not None and raw_timestamp < self.start_timestamp:
                    continue
                if self.end_timestamp is not None and raw_timestamp >= self.end_timestamp:
                    break

                if first_selected_timestamp is None:
                    first_selected_timestamp = raw_timestamp

                timestamp = (raw_timestamp - first_selected_timestamp) / self.scale

                # Check if we've exceeded max duration
                if self.max_duration_seconds is not None and timestamp > self.max_duration_seconds:
                    break

                request_tokens = int(row['Request tokens'])
                response_tokens = int(row['Response tokens'])
                model_type = row['Model']
                session_id = row.get('Session ID', '').strip()
                log_type = row.get('Log Type', '').strip()
                resolved_session_id = session_id or f"__row_{len(self.requests)}"
                tenant_id = self.tenant_assignments.get(
                    resolved_session_id,
                    self.default_tenant,
                )
                if self.include_tenants is not None and tenant_id not in self.include_tenants:
                    continue

                request = TraceRequest(
                    timestamp=timestamp,
                    session_id=resolved_session_id,
                    tenant_id=tenant_id,
                    request_tokens=request_tokens,
                    response_tokens=response_tokens,
                    model_type=model_type,
                    log_type=log_type,
                )
                self.requests.append(request)

    def get_inter_arrival_times(self) -> list[float]:
        """Get inter-arrival times between consecutive requests."""
        inter_arrivals = []
        previous_time = 0

        for req in self.requests:
            inter_arrival = req.timestamp - previous_time
            inter_arrivals.append(inter_arrival)
            previous_time = req.timestamp

        return inter_arrivals

    def __len__(self) -> int:
        return len(self.requests)

    def __getitem__(self, idx: int) -> TraceRequest:
        return self.requests[idx]


class BurstGPTBenchmark:
    """Main benchmark orchestrator."""

    def __init__(
        self,
        trace_path: str,
        base_url: str,
        model: str,
        output_dir: str = "results",
        scale: float = 1.0,
        num_prompts: Optional[int] = None,
        max_duration_seconds: Optional[float] = None,
        request_rate: Optional[float] = None,
        enable_streaming: bool = False,
        collect_vllm_metrics: bool = False,
        tenant_config_path: Optional[str] = None,
        default_tenant: str = "unassigned",
        start_timestamp: Optional[float] = None,
        end_timestamp: Optional[float] = None,
        include_tenants: Optional[list[str]] = None,
        timeout_seconds: int = 300,
        temperature: float = 0.0,
        kv_block_size: int = 16,
        metrics_sample_interval: float = 0.25,
        cache_pressure_kv_threshold: float = 90.0,
    ):
        """
        Initialize the benchmark.

        Args:
            trace_path: Path to BurstGPT trace CSV
            base_url: vLLM server base URL (e.g., http://localhost:8000)
            model: Model name to use for inference
            output_dir: Directory to save results
            scale: Scale factor for timestamps (higher = faster replay)
            num_prompts: Limit number of requests (None = use all)
            max_duration_seconds: Limit trace duration in seconds (e.g., 900 for 15 min)
            request_rate: Override inter-arrival times with fixed rate (requests/sec)
            enable_streaming: Use streaming mode for requests
            timeout_seconds: Timeout per request
            temperature: Sampling temperature
        """
        self.trace_path = trace_path
        self.base_url = base_url
        self.model = model
        self.output_dir = Path(output_dir)
        self.scale = scale
        self.num_prompts = num_prompts
        self.max_duration_seconds = max_duration_seconds
        self.request_rate = request_rate
        self.enable_streaming = enable_streaming
        self.collect_vllm_metrics = collect_vllm_metrics
        self.tenant_config_path = tenant_config_path
        self.default_tenant = default_tenant
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp
        self.include_tenants = include_tenants
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.kv_block_size = kv_block_size
        self.metrics_sample_interval = metrics_sample_interval
        self.cache_pressure_kv_threshold = cache_pressure_kv_threshold

        # Initialize logging
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()

        # Load trace
        self.tenant_assignments = self._load_tenant_assignments(
            tenant_config_path
        )
        self.trace_reader = BurstGPTTraceReader(
            trace_path,
            scale=scale,
            max_duration_seconds=max_duration_seconds,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            tenant_assignments=self.tenant_assignments,
            default_tenant=default_tenant,
            include_tenants=set(include_tenants) if include_tenants else None,
        )
        self.logger.info(f"Loaded {len(self.trace_reader)} requests from trace")
        if max_duration_seconds:
            self.logger.info(f"Trace limited to {max_duration_seconds}s ({max_duration_seconds/60:.1f} minutes)")
        if start_timestamp is not None or end_timestamp is not None:
            self.logger.info(
                "Trace timestamp slice: start=%s end=%s",
                start_timestamp,
                end_timestamp,
            )
        if self.tenant_assignments:
            self.logger.info(
                "Loaded %s session-to-tenant assignments from %s",
                len(self.tenant_assignments),
                tenant_config_path,
            )

        # Initialize metrics
        self.metrics = []
        self.errors = defaultdict(int)
        self.session_states: dict[str, SessionState] = defaultdict(SessionState)
        self.session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.vllm_metrics_collector: Optional[VLLMMetricsCollector] = None
        self.sampled_vllm_metrics: list[SampledVLLMMetrics] = []
        if self.collect_vllm_metrics:
            self.vllm_metrics_collector = VLLMMetricsCollector(self.base_url)

    def _load_tenant_assignments(
        self,
        tenant_config_path: Optional[str],
    ) -> dict[str, str]:
        """Load a session->tenant mapping from JSON or CSV."""
        if not tenant_config_path:
            return {}

        path = Path(tenant_config_path)
        if not path.exists():
            raise FileNotFoundError(f"Tenant config file not found: {path}")

        if path.suffix.lower() == ".json":
            with open(path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Tenant JSON config must be an object mapping session_id to tenant_id")
            return {
                str(session_id).strip(): str(tenant_id).strip()
                for session_id, tenant_id in data.items()
                if str(session_id).strip() and str(tenant_id).strip()
            }

        assignments: dict[str, str] = {}
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            required = {"session_id", "tenant_id"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(
                    "Tenant CSV config must contain headers: session_id,tenant_id"
                )
            for row in reader:
                session_id = str(row["session_id"]).strip()
                tenant_id = str(row["tenant_id"]).strip()
                if session_id and tenant_id:
                    assignments[session_id] = tenant_id
        return assignments

    def _setup_logging(self):
        """Setup logging to file and console."""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # File handler
        log_file = self.output_dir / "benchmark.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.INFO)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        if not self.logger.handlers:
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

    def _encode(self, text: str) -> list[int]:
        try:
            return self.tokenizer.encode(text, add_special_tokens=False)
        except TypeError:
            return self.tokenizer.encode(text)

    def _decode(self, token_ids: list[int]) -> str:
        try:
            return self.tokenizer.decode(
                token_ids,
                clean_up_tokenization_spaces=False,
            )
        except TypeError:
            return self.tokenizer.decode(token_ids)

    def _find_single_token_text(self) -> str:
        """Find a text fragment that reliably round-trips as a single token."""
        if hasattr(self, "_single_token_text"):
            return self._single_token_text

        candidate_ids = self._encode(" synthetic filler token")
        for token_id in candidate_ids:
            token_text = self._decode([token_id])
            if token_text and len(self._encode(token_text)) == 1:
                self._single_token_text = token_text
                return token_text

        # Fall back to a simple token-like fragment for mock tokenizers.
        self._single_token_text = " x"
        return self._single_token_text

    def _generate_exact_token_text(self, target_tokens: int) -> str:
        """Generate text that encodes to exactly target_tokens."""
        if target_tokens <= 0:
            return ""

        token_text = self._find_single_token_text()
        candidate = token_text * target_tokens
        current_tokens = len(self._encode(candidate))
        if current_tokens == target_tokens:
            return candidate

        # Fall back to direct token-id construction when the repeated fragment
        # does not round-trip exactly as a concatenated string.
        token_ids = self._encode(token_text)
        if len(token_ids) == 1:
            candidate = self._decode(token_ids * target_tokens)
            if len(self._encode(candidate)) == target_tokens:
                return candidate

        # Final fallback for approximate tokenizers.
        return "x" * max(target_tokens * 4, 1)

    def _build_prompt_for_request(
        self,
        trace_request: TraceRequest,
        session_state: SessionState,
    ) -> str:
        """Build a synthetic multi-turn prompt with exact total input tokens."""
        user_prefix = (
            f"{session_state.transcript}"
            "User:\n"
        )
        assistant_prefix = "\nAssistant:\n"

        prefix_tokens = len(self._encode(user_prefix + assistant_prefix))
        filler_tokens = trace_request.request_tokens - prefix_tokens
        if filler_tokens < 0:
            # Preserve the request size exactly even when the transcript
            # overhead is too large by dropping the synthetic headers.
            user_prefix = session_state.transcript
            assistant_prefix = "\n"
            prefix_tokens = len(self._encode(user_prefix + assistant_prefix))
            filler_tokens = max(0, trace_request.request_tokens - prefix_tokens)

        user_content = self._generate_exact_token_text(filler_tokens)
        prompt = f"{user_prefix}{user_content}{assistant_prefix}"

        actual_tokens = len(self._encode(prompt))
        if actual_tokens != trace_request.request_tokens:
            delta = trace_request.request_tokens - actual_tokens
            if delta > 0:
                prompt += self._generate_exact_token_text(delta)
            else:
                prompt = self._decode(self._encode(prompt)[:trace_request.request_tokens])

        return prompt

    def _build_synthetic_assistant_output(self, output_tokens: int) -> str:
        """Build synthetic assistant history with exact token count."""
        return self._generate_exact_token_text(output_tokens)

    def _estimate_kv_blocks(self, token_count: int) -> int:
        if token_count <= 0:
            return 0
        return math.ceil(token_count / self.kv_block_size)

    async def _sample_vllm_metrics_periodically(
        self,
        stop_event: asyncio.Event,
    ) -> None:
        """Continuously sample global vLLM metrics during the run."""
        if not self.vllm_metrics_collector:
            return

        while not stop_event.is_set():
            snapshot = await self.vllm_metrics_collector.fetch_metrics()
            if snapshot is not None:
                self.sampled_vllm_metrics.append(
                    SampledVLLMMetrics(
                        timestamp=snapshot.timestamp,
                        metrics=asdict(snapshot),
                    )
                )
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.metrics_sample_interval,
                )
            except asyncio.TimeoutError:
                continue

    def _metric_counter_delta_during_request(
        self,
        request_metric: RequestMetrics,
        counter_name: str,
    ) -> int:
        if request_metric.request_end_time <= request_metric.request_start_time:
            return 0

        overlapping = [
            sample for sample in self.sampled_vllm_metrics
            if request_metric.request_start_time <= sample.timestamp <= request_metric.request_end_time
        ]
        if not overlapping:
            return 0

        values = [
            sample.metrics.get(counter_name)
            for sample in overlapping
            if sample.metrics.get(counter_name) is not None
        ]
        if not values:
            return 0
        return max(0, int(values[-1] - values[0]))

    def _request_overlaps_high_kv_pressure(
        self,
        request_metric: RequestMetrics,
    ) -> bool:
        return any(
            request_metric.request_start_time <= sample.timestamp <= request_metric.request_end_time
            and (sample.metrics.get("kv_cache_usage_pct") or 0.0) >= self.cache_pressure_kv_threshold
            for sample in self.sampled_vllm_metrics
        )

    def _estimated_active_kv_blocks_at(self, timestamp: float) -> dict[str, int]:
        active_by_tenant: dict[str, int] = defaultdict(int)
        for metric in self.metrics:
            if metric.error is not None:
                continue
            if metric.request_start_time <= timestamp <= metric.request_end_time:
                active_by_tenant[metric.tenant_id] += metric.estimated_peak_kv_blocks
        return dict(active_by_tenant)

    def _annotate_requests_with_cache_pressure(self) -> None:
        if not self.sampled_vllm_metrics:
            return

        for metric in self.metrics:
            metric.overlapping_swap_events = self._metric_counter_delta_during_request(
                metric, "num_requests_swapped"
            )
            metric.overlapping_preemption_events = self._metric_counter_delta_during_request(
                metric, "num_preemptions"
            )
            metric.overlapping_context_swap_out_events = self._metric_counter_delta_during_request(
                metric, "num_context_swap_out"
            )
            metric.overlapping_context_swap_in_events = self._metric_counter_delta_during_request(
                metric, "num_context_swap_in"
            )
            metric.approximate_recompute_events = (
                metric.overlapping_preemption_events
                + metric.overlapping_context_swap_in_events
            )
            metric.approximate_recompute_cost_tokens = (
                metric.approximate_recompute_events * metric.actual_input_tokens
            )

            harm_reasons: list[str] = []
            if self._request_overlaps_high_kv_pressure(metric):
                harm_reasons.append("high_kv_cache_usage")
            if metric.overlapping_swap_events > 0:
                harm_reasons.append("swap_overlap")
            if metric.overlapping_preemption_events > 0:
                harm_reasons.append("preemption_overlap")
            if metric.overlapping_context_swap_out_events > 0:
                harm_reasons.append("context_swap_out_overlap")
            if metric.overlapping_context_swap_in_events > 0:
                harm_reasons.append("context_swap_in_overlap")

            metric.cache_pressure_harm_reasons = harm_reasons
            metric.cache_pressure_harmed = bool(harm_reasons)

    async def _send_request(
        self,
        request_id: int,
        trace_request: TraceRequest,
        prompt: str,
        session: aiohttp.ClientSession,
    ) -> RequestMetrics:
        """Send a single request to the vLLM server."""
        metrics = RequestMetrics(
            request_id=request_id,
            timestamp=time.time(),
            request_tokens=trace_request.request_tokens,
            expected_output_tokens=trace_request.response_tokens,
            actual_input_tokens=0,
            actual_output_tokens=0,
            time_to_first_token=0.0,
            total_latency=0.0,
            session_id=trace_request.session_id,
            tenant_id=trace_request.tenant_id,
            log_type=trace_request.log_type,
            cache_pressure_harm_reasons=[],
        )

        try:
            url = f"{self.base_url}/v1/completions"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "max_tokens": trace_request.response_tokens,
                "temperature": self.temperature,
                "stream": self.enable_streaming,
            }
            if trace_request.response_tokens > 0:
                payload["min_tokens"] = trace_request.response_tokens

            start_time = time.perf_counter()
            wall_start_time = time.time()
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

            async with session.post(
                url,
                json=payload,
                timeout=timeout
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    metrics.error = f"HTTP {resp.status}: {error_text[:100]}"
                    return metrics

                if self.enable_streaming:
                    first_token_time = None
                    output_text = ""

                    async for line in resp.content:
                        if not line:
                            continue

                        decoded = line.decode("utf-8", errors="ignore").strip()
                        if not decoded.startswith("data: "):
                            continue

                        payload_line = decoded[6:]
                        if payload_line == "[DONE]":
                            continue

                        if first_token_time is None:
                            first_token_time = time.perf_counter() - start_time
                            metrics.time_to_first_token = first_token_time

                        try:
                            data = json.loads(payload_line)
                            if "choices" in data:
                                output_text += data["choices"][0].get("text", "")
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass

                    metrics.actual_output_tokens = len(
                        self._encode(output_text)
                    )
                else:
                    # Non-streaming response
                    data = await resp.json()
                    output_text = data["choices"][0]["text"]
                    metrics.actual_output_tokens = len(
                        self._encode(output_text)
                    )
                    metrics.time_to_first_token = time.perf_counter() - start_time

            metrics.total_latency = time.perf_counter() - start_time
            metrics.actual_input_tokens = len(self._encode(prompt))
            metrics.request_start_time = wall_start_time
            metrics.request_end_time = wall_start_time + metrics.total_latency
            metrics.estimated_prefill_kv_tokens = metrics.actual_input_tokens
            metrics.estimated_peak_kv_tokens = (
                metrics.actual_input_tokens + metrics.actual_output_tokens
            )
            metrics.estimated_prefill_kv_blocks = self._estimate_kv_blocks(
                metrics.estimated_prefill_kv_tokens
            )
            metrics.estimated_peak_kv_blocks = self._estimate_kv_blocks(
                metrics.estimated_peak_kv_tokens
            )

        except asyncio.TimeoutError:
            metrics.error = f"Request timeout after {self.timeout_seconds}s"
        except Exception as e:
            metrics.error = f"Request failed: {str(e)[:100]}"

        return metrics

    async def run(self):
        """Run the benchmark."""
        self.logger.info("="*80)
        self.logger.info("Starting BurstGPT Trace Replay Benchmark")
        self.logger.info("="*80)
        self.logger.info(f"Trace: {self.trace_path}")
        self.logger.info(f"Model: {self.model}")
        self.logger.info(f"Base URL: {self.base_url}")
        self.logger.info(f"Scale: {self.scale}x")
        self.logger.info(f"Streaming: {self.enable_streaming}")
        self.logger.info(f"Collect vLLM metrics: {self.collect_vllm_metrics}")
        self.logger.info(f"Default tenant: {self.default_tenant}")
        if self.include_tenants:
            self.logger.info(f"Included tenants: {', '.join(self.include_tenants)}")
        if self.start_timestamp is not None or self.end_timestamp is not None:
            self.logger.info(
                "Trace timestamp window: start=%s end=%s",
                self.start_timestamp,
                self.end_timestamp,
            )

        # Load tokenizer for token counting
        try:
            from transformers import AutoTokenizer
            model_id = self.model.replace("_", "/")
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_id, trust_remote_code=True
            )
            self.logger.info(f"Loaded tokenizer for {model_id}")
        except Exception as e:
            self.logger.error(f"Failed to load tokenizer: {e}")
            self.logger.warning("Using mock tokenizer (token counts may be inaccurate)")
            self.tokenizer = MockTokenizer()

        # Determine number of requests
        num_requests = (
            self.num_prompts if self.num_prompts else len(self.trace_reader)
        )
        self.logger.info(f"Total requests to send: {num_requests}")

        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        connector = aiohttp.TCPConnector(limit=100)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        ) as session:
            metrics_stop_event = asyncio.Event()
            metrics_sampler_task = None
            if self.vllm_metrics_collector:
                await self.vllm_metrics_collector.initialize()
                metrics_sampler_task = asyncio.create_task(
                    self._sample_vllm_metrics_periodically(metrics_stop_event)
                )

            # Check server health
            try:
                async with session.get(f"{self.base_url}/v1/models") as resp:
                    if resp.status == 200:
                        self.logger.info("Server is ready")
                    else:
                        self.logger.error("Server is not responding properly")
                        return
            except Exception as e:
                self.logger.error(f"Failed to connect to server: {e}")
                return

            # Send requests
            start_time = time.perf_counter()
            tasks = []

            for request_id in tqdm(
                range(num_requests),
                desc="Scheduling requests",
                total=num_requests
            ):
                trace_request = self.trace_reader[request_id]

                if self.request_rate is not None:
                    scheduled_offset = request_id / self.request_rate
                else:
                    scheduled_offset = trace_request.timestamp

                tasks.append(asyncio.create_task(
                    self._run_scheduled_request(
                        request_id=request_id,
                        trace_request=trace_request,
                        scheduled_offset=scheduled_offset,
                        benchmark_start=start_time,
                        session=session,
                    )
                ))

            self.metrics = await asyncio.gather(*tasks)
            self.metrics.sort(key=lambda metric: metric.request_id)

            if self.vllm_metrics_collector:
                metrics_stop_event.set()
                if metrics_sampler_task:
                    await metrics_sampler_task
                final_snapshot = await self.vllm_metrics_collector.fetch_metrics()
                if final_snapshot is not None:
                    self.sampled_vllm_metrics.append(
                        SampledVLLMMetrics(
                            timestamp=final_snapshot.timestamp,
                            metrics=asdict(final_snapshot),
                        )
                    )
                await self.vllm_metrics_collector.shutdown()

        # Post-processing
        self._annotate_requests_with_cache_pressure()
        self._populate_estimated_kv_shares()
        total_time = time.perf_counter() - start_time
        self._print_summary(total_time)
        self._save_results()

    def _populate_estimated_kv_shares(self) -> None:
        total_peak_blocks = sum(
            metric.estimated_peak_kv_blocks
            for metric in self.metrics
            if metric.error is None
        )
        if total_peak_blocks <= 0:
            return
        for metric in self.metrics:
            if metric.error is None:
                metric.estimated_kv_footprint_share = (
                    metric.estimated_peak_kv_blocks / total_peak_blocks
                )

    async def _run_scheduled_request(
        self,
        request_id: int,
        trace_request: TraceRequest,
        scheduled_offset: float,
        benchmark_start: float,
        session: aiohttp.ClientSession,
    ) -> RequestMetrics:
        """Dispatch one request at its scheduled wall-clock time."""
        sleep_duration = scheduled_offset - (time.perf_counter() - benchmark_start)
        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

        lock = self.session_locks[trace_request.session_id]
        async with lock:
            session_state = self.session_states[trace_request.session_id]
            prompt = self._build_prompt_for_request(
                trace_request,
                session_state,
            )
            metrics_before = None
            if self.vllm_metrics_collector:
                snapshot = await self.vllm_metrics_collector.fetch_metrics()
                if snapshot is not None:
                    metrics_before = asdict(snapshot)
            metrics = await self._send_request(
                request_id=request_id,
                trace_request=trace_request,
                prompt=prompt,
                session=session,
            )
            if self.vllm_metrics_collector:
                snapshot = await self.vllm_metrics_collector.fetch_metrics()
                if snapshot is not None:
                    metrics.vllm_metrics_after = asdict(snapshot)
            metrics.vllm_metrics_before = metrics_before

            synthetic_output = self._build_synthetic_assistant_output(
                trace_request.response_tokens
            )
            session_state.synthetic_turn_index += 1
            session_state.transcript = (
                f"{prompt}{synthetic_output}\n"
            )

        if metrics.error:
            self.errors[metrics.error] += 1
            self.logger.warning(
                f"Request {request_id} failed: {metrics.error}"
            )
        elif metrics.actual_input_tokens != trace_request.request_tokens:
            self.logger.warning(
                "Request %s session %s input token mismatch: expected=%s actual=%s",
                request_id,
                trace_request.session_id,
                trace_request.request_tokens,
                metrics.actual_input_tokens,
            )
        elif metrics.actual_output_tokens != trace_request.response_tokens:
            self.logger.warning(
                "Request %s session %s output token mismatch: expected=%s actual=%s",
                request_id,
                trace_request.session_id,
                trace_request.response_tokens,
                metrics.actual_output_tokens,
            )

        return metrics

    def _print_summary(self, total_time: float):
        """Print benchmark summary statistics."""
        self.logger.info("="*80)
        self.logger.info("Benchmark Summary")
        self.logger.info("="*80)

        successful = sum(1 for m in self.metrics if m.error is None)
        failed = len(self.metrics) - successful

        self.logger.info(f"Total requests: {len(self.metrics)}")
        self.logger.info(f"Successful: {successful}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Success rate: {100*successful/len(self.metrics):.2f}%")

        if failed > 0:
            self.logger.info("\nError breakdown:")
            for error, count in self.errors.items():
                self.logger.info(f"  {error}: {count}")

        # Latency statistics (only for successful requests)
        successful_metrics = [m for m in self.metrics if m.error is None]

        if successful_metrics:
            latencies = [m.total_latency for m in successful_metrics]
            ttft_times = [m.time_to_first_token for m in successful_metrics]
            tbt_times = [
                (m.total_latency - m.time_to_first_token) / max(m.actual_output_tokens, 1)
                for m in successful_metrics
                if m.total_latency >= m.time_to_first_token
            ]

            self.logger.info("\nLatency Statistics (successful requests only):")
            self.logger.info(f"  Total latency:")
            self.logger.info(f"    Mean: {np.mean(latencies):.3f}s")
            self.logger.info(f"    Median: {np.median(latencies):.3f}s")
            self.logger.info(f"    P99: {np.percentile(latencies, 99):.3f}s")
            self.logger.info(f"    P95: {np.percentile(latencies, 95):.3f}s")

            self.logger.info(f"  Time to first token:")
            self.logger.info(f"    Mean: {np.mean(ttft_times)*1000:.2f}ms")
            self.logger.info(f"    Median: {np.median(ttft_times)*1000:.2f}ms")
            self.logger.info(f"    P99: {np.percentile(ttft_times, 99)*1000:.2f}ms")
            if tbt_times:
                self.logger.info(f"  Time between tokens:")
                self.logger.info(f"    Mean: {np.mean(tbt_times)*1000:.2f}ms/token")
                self.logger.info(f"    Median: {np.median(tbt_times)*1000:.2f}ms/token")
                self.logger.info(f"    P99: {np.percentile(tbt_times, 99)*1000:.2f}ms/token")

            self.logger.info(f"\nThroughput:")
            self.logger.info(f"  Requests/sec: {successful/total_time:.2f}")

            # Token statistics
            total_input = sum(m.actual_input_tokens for m in successful_metrics)
            total_output = sum(m.actual_output_tokens for m in successful_metrics)

            self.logger.info(f"\nToken Statistics:")
            self.logger.info(f"  Total input tokens: {total_input}")
            self.logger.info(f"  Total output tokens: {total_output}")
            self.logger.info(f"  Input tokens/sec: {total_input/total_time:.2f}")
            self.logger.info(f"  Output tokens/sec: {total_output/total_time:.2f}")

        tenant_summary = self._build_per_tenant_summary()
        if tenant_summary:
            self.logger.info("\nPer-tenant Summary:")
            for tenant_id, summary in sorted(tenant_summary.items()):
                self.logger.info(
                    "  %s: requests=%s success=%s mean_latency=%.3fs mean_ttft=%.2fms peak_est_kv_blocks=%s harmed_frac=%.3f",
                    tenant_id,
                    summary["total_requests"],
                    summary["successful_requests"],
                    summary["latency_mean"],
                    summary["ttft_mean_ms"],
                    summary["peak_estimated_active_kv_blocks"],
                    summary["cache_pressure_harmed_fraction"],
                )

        self.logger.info(f"\nTotal benchmark time: {total_time:.2f}s")

    def _save_results(self):
        """Save detailed results to JSON and CSV files."""
        # Save as JSON
        results = {
            "benchmark_config": {
                "trace_path": str(self.trace_path),
                "model": self.model,
                "base_url": self.base_url,
                "scale": self.scale,
                "streaming": self.enable_streaming,
                "collect_vllm_metrics": self.collect_vllm_metrics,
                "tenant_config_path": self.tenant_config_path,
                "default_tenant": self.default_tenant,
                "include_tenants": self.include_tenants,
                "start_timestamp": self.start_timestamp,
                "end_timestamp": self.end_timestamp,
                "kv_block_size": self.kv_block_size,
                "metrics_sample_interval": self.metrics_sample_interval,
                "cache_pressure_kv_threshold": self.cache_pressure_kv_threshold,
                "timestamp": datetime.now().isoformat(),
            },
            "summary": {
                "total_requests": len(self.metrics),
                "successful_requests": sum(1 for m in self.metrics if m.error is None),
                "failed_requests": sum(1 for m in self.metrics if m.error is not None),
                "per_tenant_summary": self._build_per_tenant_summary(),
                "tbt_summary_ms_per_token": self._build_tbt_summary(),
                "vllm_metrics_summary": self._build_vllm_metrics_summary(),
                "cache_pressure_summary": self._build_cache_pressure_summary(),
                "active_kv_footprint_summary": self._build_active_kv_footprint_summary(),
                "metric_notes": {
                    "estimated_kv_fields": "Client-side estimates from prompt/output token counts and configured kv block size.",
                    "cache_pressure_harmed": "Overlap-based flag using sampled global vLLM metrics, not exact per-request server attribution.",
                    "recompute_fields": "Approximate overlap-based proxies from global preemption/context-swap counters.",
                },
            },
            "metrics": [asdict(m) for m in self.metrics],
            "vllm_metric_samples": [asdict(sample) for sample in self.sampled_vllm_metrics],
        }

        results_json = self.output_dir / "results.json"
        with open(results_json, 'w') as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Results saved to {results_json}")

        # Save as CSV for easy analysis
        if self.metrics:
            import csv
            results_csv = self.output_dir / "results.csv"
            with open(results_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=asdict(self.metrics[0]).keys())
                writer.writeheader()
                for m in self.metrics:
                    writer.writerow(asdict(m))
            self.logger.info(f"Results saved to {results_csv}")

    def _build_vllm_metrics_summary(self) -> dict[str, Any]:
        """Aggregate vLLM metrics snapshots collected during the run."""
        if not self.collect_vllm_metrics:
            return {}

        before_snapshots = [
            m.vllm_metrics_before for m in self.metrics if m.vllm_metrics_before
        ]
        after_snapshots = [
            m.vllm_metrics_after for m in self.metrics if m.vllm_metrics_after
        ]
        snapshots = before_snapshots + after_snapshots
        if not snapshots:
            return {}

        def values(key: str) -> list[float]:
            return [
                s[key] for s in snapshots
                if s.get(key) is not None
            ]

        summary: dict[str, Any] = {
            "num_snapshots": len(snapshots),
        }

        metric_names = [
            "kv_cache_usage_pct",
            "num_requests_running",
            "num_requests_waiting",
            "num_requests_swapped",
            "num_preemptions",
            "num_context_swap_out",
            "num_context_swap_in",
            "total_tokens_generated",
            "total_input_tokens",
            "avg_iteration_latency_ms",
        ]
        for name in metric_names:
            vals = values(name)
            if vals:
                summary[name] = {
                    "min": min(vals),
                    "max": max(vals),
                    "mean": float(np.mean(vals)),
                }

        return summary

    def _build_active_kv_footprint_summary(self) -> dict[str, Any]:
        if not self.sampled_vllm_metrics:
            return {}

        per_tenant_peak_blocks: dict[str, int] = defaultdict(int)
        per_tenant_area_blocks_seconds: dict[str, float] = defaultdict(float)
        global_peak_blocks = 0
        total_area_blocks_seconds = 0.0

        for idx, sample in enumerate(self.sampled_vllm_metrics):
            active_by_tenant = self._estimated_active_kv_blocks_at(sample.timestamp)
            total_active = sum(active_by_tenant.values())
            global_peak_blocks = max(global_peak_blocks, total_active)

            next_timestamp = (
                self.sampled_vllm_metrics[idx + 1].timestamp
                if idx + 1 < len(self.sampled_vllm_metrics)
                else sample.timestamp
            )
            duration = max(0.0, next_timestamp - sample.timestamp)
            total_area_blocks_seconds += total_active * duration

            for tenant_id, blocks in active_by_tenant.items():
                per_tenant_peak_blocks[tenant_id] = max(
                    per_tenant_peak_blocks[tenant_id],
                    blocks,
                )
                per_tenant_area_blocks_seconds[tenant_id] += blocks * duration

        return {
            "num_samples": len(self.sampled_vllm_metrics),
            "global_peak_estimated_active_kv_blocks": global_peak_blocks,
            "global_mean_estimated_active_kv_blocks": (
                total_area_blocks_seconds
                / max(
                    self.sampled_vllm_metrics[-1].timestamp - self.sampled_vllm_metrics[0].timestamp,
                    1e-9,
                )
            ),
            "per_tenant_peak_estimated_active_kv_blocks": dict(per_tenant_peak_blocks),
            "per_tenant_mean_estimated_active_kv_blocks": {
                tenant_id: (
                    area
                    / max(
                        self.sampled_vllm_metrics[-1].timestamp - self.sampled_vllm_metrics[0].timestamp,
                        1e-9,
                    )
                )
                for tenant_id, area in per_tenant_area_blocks_seconds.items()
            },
        }

    def _build_cache_pressure_summary(self) -> dict[str, Any]:
        successful = [m for m in self.metrics if m.error is None]
        if not successful:
            return {}

        harmed = [m for m in successful if m.cache_pressure_harmed]
        reasons = defaultdict(int)
        for metric in harmed:
            for reason in metric.cache_pressure_harm_reasons:
                reasons[reason] += 1

        return {
            "successful_requests": len(successful),
            "harmed_requests": len(harmed),
            "harmed_fraction": len(harmed) / len(successful),
            "harm_reason_counts": dict(reasons),
            "approximate_recompute_events": int(
                sum(m.approximate_recompute_events for m in successful)
            ),
            "approximate_recompute_cost_tokens": int(
                sum(m.approximate_recompute_cost_tokens for m in successful)
            ),
        }

    def _build_per_tenant_summary(self) -> dict[str, dict[str, Any]]:
        """Aggregate core replay metrics by tenant label."""
        grouped: dict[str, list[RequestMetrics]] = defaultdict(list)
        for metric in self.metrics:
            grouped[metric.tenant_id].append(metric)

        summary: dict[str, dict[str, Any]] = {}
        for tenant_id, tenant_metrics in grouped.items():
            successful = [m for m in tenant_metrics if m.error is None]
            latencies = [m.total_latency for m in successful]
            ttfts = [m.time_to_first_token for m in successful]
            tbts = [
                (m.total_latency - m.time_to_first_token) / max(m.actual_output_tokens, 1)
                for m in successful
                if m.total_latency >= m.time_to_first_token
            ]
            total_requests = len(tenant_metrics)
            successful_requests = len(successful)
            harmed = [m for m in successful if m.cache_pressure_harmed]
            request_share = total_requests / max(len(self.metrics), 1)
            kv_share = sum(
                m.estimated_peak_kv_blocks for m in successful
            ) / max(
                sum(
                    other.estimated_peak_kv_blocks
                    for other in self.metrics
                    if other.error is None
                ),
                1,
            )
            active_summary = self._build_active_kv_footprint_summary()
            summary[tenant_id] = {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": total_requests - successful_requests,
                "latency_mean": float(np.mean(latencies)) if latencies else 0.0,
                "latency_p95": float(np.percentile(latencies, 95)) if latencies else 0.0,
                "latency_p99": float(np.percentile(latencies, 99)) if latencies else 0.0,
                "ttft_mean_ms": float(np.mean(ttfts) * 1000) if ttfts else 0.0,
                "ttft_p95_ms": float(np.percentile(ttfts, 95) * 1000) if ttfts else 0.0,
                "ttft_p99_ms": float(np.percentile(ttfts, 99) * 1000) if ttfts else 0.0,
                "tbt_mean_ms_per_token": float(np.mean(tbts) * 1000) if tbts else 0.0,
                "tbt_p95_ms_per_token": float(np.percentile(tbts, 95) * 1000) if tbts else 0.0,
                "tbt_p99_ms_per_token": float(np.percentile(tbts, 99) * 1000) if tbts else 0.0,
                "mean_input_tokens": (
                    float(np.mean([m.actual_input_tokens for m in successful]))
                    if successful else 0.0
                ),
                "mean_output_tokens": (
                    float(np.mean([m.actual_output_tokens for m in successful]))
                    if successful else 0.0
                ),
                "mean_estimated_prefill_kv_blocks": (
                    float(np.mean([m.estimated_prefill_kv_blocks for m in successful]))
                    if successful else 0.0
                ),
                "mean_estimated_peak_kv_blocks": (
                    float(np.mean([m.estimated_peak_kv_blocks for m in successful]))
                    if successful else 0.0
                ),
                "peak_estimated_active_kv_blocks": active_summary.get(
                    "per_tenant_peak_estimated_active_kv_blocks", {}
                ).get(tenant_id, 0),
                "mean_estimated_active_kv_blocks": active_summary.get(
                    "per_tenant_mean_estimated_active_kv_blocks", {}
                ).get(tenant_id, 0.0),
                "request_share": request_share,
                "estimated_kv_share": kv_share,
                "estimated_kv_share_to_request_share_ratio": (
                    kv_share / request_share if request_share > 0 else 0.0
                ),
                "cache_pressure_harmed_fraction": (
                    len(harmed) / successful_requests if successful_requests else 0.0
                ),
                "approximate_swap_overlap_events": int(
                    sum(m.overlapping_swap_events for m in successful)
                ),
                "approximate_preemption_overlap_events": int(
                    sum(m.overlapping_preemption_events for m in successful)
                ),
                "approximate_recompute_events": int(
                    sum(m.approximate_recompute_events for m in successful)
                ),
                "approximate_recompute_cost_tokens": int(
                    sum(m.approximate_recompute_cost_tokens for m in successful)
                ),
            }
        return summary

    def _build_tbt_summary(self) -> dict[str, float]:
        successful = [m for m in self.metrics if m.error is None]
        tbts = [
            (m.total_latency - m.time_to_first_token) / max(m.actual_output_tokens, 1)
            for m in successful
            if m.total_latency >= m.time_to_first_token
        ]
        if not tbts:
            return {}
        return {
            "mean": float(np.mean(tbts) * 1000),
            "median": float(np.median(tbts) * 1000),
            "p95": float(np.percentile(tbts, 95) * 1000),
            "p99": float(np.percentile(tbts, 99) * 1000),
        }


class MockTokenizer:
    """Mock tokenizer when transformers is unavailable."""

    def encode(self, text: str) -> list[int]:
        """Approximate token count (roughly 4 chars per token)."""
        return list(range(len(text) // 4))

    def decode(self, token_ids: list[int]) -> str:
        return " " * (len(token_ids) * 4)


def main():
    parser = argparse.ArgumentParser(
        description="BurstGPT Trace Replay Benchmark for vLLM"
    )
    parser.add_argument(
        "--trace-path",
        type=str,
        required=True,
        help="Path to BurstGPT trace CSV file",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="vLLM server base URL",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model name to use for inference",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory to save benchmark results",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Scale factor for timestamps (>1 = faster replay)",
    )
    parser.add_argument(
        "--num-prompts",
        type=int,
        default=None,
        help="Limit number of requests to send",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=None,
        help="Limit trace duration in seconds (e.g., 900 for 15 minutes)",
    )
    parser.add_argument(
        "--request-rate",
        type=float,
        default=None,
        help="Override inter-arrival times with fixed rate (requests/sec)",
    )
    parser.add_argument(
        "--enable-streaming",
        action="store_true",
        help="Use streaming mode for requests",
    )
    parser.add_argument(
        "--collect-vllm-metrics",
        action="store_true",
        help="Collect server-side vLLM metrics from /metrics",
    )
    parser.add_argument(
        "--tenant-config",
        type=str,
        default=None,
        help="Path to JSON or CSV mapping session_id to tenant_id",
    )
    parser.add_argument(
        "--default-tenant",
        type=str,
        default="unassigned",
        help="Tenant label for sessions not present in --tenant-config",
    )
    parser.add_argument(
        "--start-timestamp",
        type=float,
        default=None,
        help="Absolute trace timestamp to start replay from.",
    )
    parser.add_argument(
        "--end-timestamp",
        type=float,
        default=None,
        help="Absolute trace timestamp to stop replay before.",
    )
    parser.add_argument(
        "--include-tenants",
        type=str,
        default=None,
        help="Comma-separated tenant ids to replay, e.g. tenant_a or tenant_a,tenant_b",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Request timeout in seconds",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature",
    )
    parser.add_argument(
        "--kv-block-size",
        type=int,
        default=16,
        help="Approximate KV block size in tokens for estimated KV metrics.",
    )
    parser.add_argument(
        "--metrics-sample-interval",
        type=float,
        default=0.25,
        help="Sampling interval in seconds for polling /metrics during replay.",
    )
    parser.add_argument(
        "--cache-pressure-kv-threshold",
        type=float,
        default=90.0,
        help="KV cache usage percentage threshold for marking cache-pressure overlap.",
    )

    args = parser.parse_args()

    benchmark = BurstGPTBenchmark(
        trace_path=args.trace_path,
        base_url=args.base_url,
        model=args.model,
        output_dir=args.output_dir,
        scale=args.scale,
        num_prompts=args.num_prompts,
        max_duration_seconds=args.max_duration,
        request_rate=args.request_rate,
        enable_streaming=args.enable_streaming,
        collect_vllm_metrics=args.collect_vllm_metrics,
        tenant_config_path=args.tenant_config,
        default_tenant=args.default_tenant,
        start_timestamp=args.start_timestamp,
        end_timestamp=args.end_timestamp,
        include_tenants=(
            [tenant.strip() for tenant in args.include_tenants.split(",") if tenant.strip()]
            if args.include_tenants else None
        ),
        timeout_seconds=args.timeout,
        temperature=args.temperature,
        kv_block_size=args.kv_block_size,
        metrics_sample_interval=args.metrics_sample_interval,
        cache_pressure_kv_threshold=args.cache_pressure_kv_threshold,
    )

    asyncio.run(benchmark.run())


if __name__ == "__main__":
    main()
