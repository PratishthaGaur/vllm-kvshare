# vLLM Metrics Collection Guide

Enhanced benchmarking with detailed vLLM server metrics collection.

## Overview

Beyond basic latency and throughput metrics, you can now collect vLLM-specific performance metrics:

- **KV Cache**: Usage, pressure, recomputation tracking
- **Scheduling**: Queue delays, preemption events, wait times
- **Engine**: Running requests, swapped context, iteration patterns
- **System**: GPU cache usage, request queue depth

## What Metrics Are Collected?

### 1. KV Cache Metrics

**Per-Request:**
- `kv_cache_delta_blocks`: Change in used KV cache blocks during request
- `kv_cache_recompute_pct`: Estimated % of KV cache that was recomputed
- `kv_cache_hit_rate`: Estimated cache hit rate during execution

**Aggregate:**
- `kv_cache_usage_pct`: Peak KV cache memory usage (0-100%)
- `kv_cache_total_blocks`: Total available KV cache blocks
- `kv_cache_used_blocks`: Currently allocated blocks
- `kv_cache_free_blocks`: Available blocks

### 2. Scheduling Metrics

**Per-Request:**
- `scheduling_delay_ms`: Time request waited in queue before execution
- `queue_wait_start`: When request was queued
- `execution_start`: When execution actually started
- `num_preemptions`: How many times request was preempted

**Aggregate:**
- `num_requests_running`: Currently executing requests
- `num_requests_waiting`: Waiting in queue
- `num_requests_swapped`: Waiting due to KV cache pressure

### 3. Engine Metrics

**Per-Request:**
- `actual_execution_time`: Time spent in actual execution (wall clock)
- `tokens_generated_during_request`: Tokens this request generated
- `engine_utilization_pct`: % of engine capacity used

**Aggregate:**
- `num_context_swap_out`: Total context swaps to disk
- `num_context_swap_in`: Total context swaps back to GPU
- `num_preemptions_total`: Total preemption events
- `iteration_tokens_distribution`: Histogram of tokens per scheduler iteration

## How Metrics Are Collected

### Architecture

```
For each request:
  ↓
1. Snapshot vLLM metrics BEFORE request
   ├─ KV cache usage
   ├─ Request queue depth
   ├─ Total preemptions so far
   └─ Total tokens generated so far
  ↓
2. Send request to vLLM
   └─ Request executes with various scheduling/preemption events
  ↓
3. Snapshot vLLM metrics AFTER request
   ├─ KV cache usage (new)
   ├─ Request queue depth (new)
   ├─ Total preemptions (new)
   └─ Total tokens generated (new)
  ↓
4. Calculate deltas
   ├─ ΔKV_cache = after - before
   ├─ ΔPreemptions = after - before
   ├─ ΔTokens = after - before
   └─ SchedulingDelay = execution_start - queue_start
```

### Metric Sources

Metrics come from vLLM's `/metrics` endpoint (Prometheus format):

```bash
curl http://localhost:8000/metrics | grep vllm
```

Available metrics:
- `vllm:gpu_cache_usage_perc` - KV cache GPU memory %
- `vllm:num_preemptions_total` - Total preemptions count
- `vllm:context_swap_in_total` - Context swaps to GPU
- `vllm:context_swap_out_total` - Context swaps to disk
- `vllm:num_requests_running` - Currently running requests
- `vllm:num_requests_waiting` - Waiting in queue
- `vllm:tokens_generated_total` - Total tokens generated

## Output Format

### Per-Request Metrics (in results.json)

```json
{
  "request_id": 0,
  "timestamp": 5.23,
  "request_tokens": 472,
  "expected_output_tokens": 18,
  "actual_input_tokens": 472,
  "actual_output_tokens": 18,
  "time_to_first_token": 0.142,
  "total_latency": 0.384,
  "error": null,

  // NEW: vLLM metrics
  "scheduling_delay_ms": 12.5,
  "kv_cache_delta_blocks": 15,
  "num_preemptions": 0,
  "tokens_generated_during_request": 18,
  "actual_execution_time": 0.350,

  // Detailed snapshots
  "vllm_metrics_before": {
    "timestamp": 1711094415.234,
    "kv_cache_usage_pct": 45.2,
    "kv_cache_used_blocks": 2245,
    "num_requests_running": 3,
    "num_requests_waiting": 8,
    "num_preemptions": 12,
    "total_tokens_generated": 5430
  },
  "vllm_metrics_after": {
    "timestamp": 1711094415.624,
    "kv_cache_usage_pct": 47.8,
    "kv_cache_used_blocks": 2260,
    "num_requests_running": 2,
    "num_requests_waiting": 7,
    "num_preemptions": 12,
    "total_tokens_generated": 5448
  }
}
```

### Aggregate Statistics

Added to logs and summary:

```
KV Cache Statistics:
  Peak usage: 75.3%
  Avg delta per request: 18 blocks
  Max delta: 45 blocks
  Min delta: 2 blocks

Scheduling Statistics:
  Avg scheduling delay: 15.4ms
  P95 scheduling delay: 45.2ms
  P99 scheduling delay: 87.5ms
  Max scheduling delay: 150.2ms

Preemption Statistics:
  Total preemptions: 23
  Requests preempted: 18 (1.8%)
  Avg preemptions per request: 0.023

Context Swap Statistics:
  Total swaps to disk: 5
  Total swaps to GPU: 5
  Swap overhead estimate: ~45ms per swap
```

## Usage Example

### Basic Usage (Automatic Metrics Collection)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/with_vllm_metrics \
    --collect-vllm-metrics
```

### Analysis

```bash
# View KV cache stats
python -c "
import json
with open('results/with_vllm_metrics/results.json') as f:
    data = json.load(f)
successful = [m for m in data['metrics'] if not m['error']]
kv_deltas = [m['kv_cache_delta_blocks'] for m in successful if m.get('kv_cache_delta_blocks')]
print(f'Avg KV cache delta: {sum(kv_deltas)/len(kv_deltas):.1f} blocks')
print(f'Max KV cache delta: {max(kv_deltas)} blocks')
"

# View scheduling delays
python -c "
import json, numpy as np
with open('results/with_vllm_metrics/results.json') as f:
    data = json.load(f)
successful = [m for m in data['metrics'] if not m['error']]
delays = [m['scheduling_delay_ms'] for m in successful if m.get('scheduling_delay_ms')]
print(f'Avg scheduling delay: {np.mean(delays):.1f}ms')
print(f'P99 scheduling delay: {np.percentile(delays, 99):.1f}ms')
"
```

## Interpreting Metrics

### KV Cache Delta

```
kv_cache_delta_blocks = 15

↓ What this means:
  - Request allocated 15 new KV cache blocks
  - This is CUMULATIVE across all prefill phases

↓ Why it matters:
  - Large delta = long context or slow prefill
  - Sudden spikes might indicate cache allocation issues
  - Negative delta = blocks were freed (end of request)

↓ What to watch:
  - If delta > available blocks → preemption happens
  - If delta consistently high → memory pressure
```

### Scheduling Delay

```
scheduling_delay_ms = 12.5

↓ What this means:
  - Request waited 12.5ms in queue before execution
  - This is QUEUEING DELAY, not execution time

↓ Why it matters:
  - High delay = system overloaded or slow prefill
  - Indicates request was blocked waiting for resources
  - Critical for measuring perceived latency

↓ What to watch:
  - If > 50ms = noticeable queueing
  - If > 200ms = significant queue backlog
  - Correlate with num_requests_waiting for confirmation
```

### Preemptions

```
num_preemptions = 1

↓ What this means:
  - Request was preempted 1 time during execution
  - KV cache was temporarily moved to disk
  - Request was resumed later

↓ Why it matters:
  - Preemption = extra latency
  - Each preemption typically adds 20-100ms
  - Indicates KV cache pressure

↓ What to watch:
  - If > 0 for most requests = severe memory pressure
  - If growing over time = system degrading
  - Correlate with kv_cache_usage_pct
```

### Actual Execution Time

```
actual_execution_time = 350ms
total_latency = 384ms
scheduling_delay_ms = 12.5ms

↓ Latency breakdown:
  Scheduling Delay (12.5ms) + Execution (350ms) + Network (21.5ms) = 384ms

↓ This tells you:
  - Request spent 91% of time in actual execution
  - Only 3% waiting in queue
  - ~5% network/other overhead
```

## Comparison: With and Without Metrics

### Baseline Results

```
Request #0:
  request_tokens: 472
  expected_output_tokens: 18
  total_latency: 0.384s
  time_to_first_token: 0.142s
```

### With vLLM Metrics

```
Request #0:
  request_tokens: 472
  expected_output_tokens: 18
  total_latency: 0.384s
  time_to_first_token: 0.142s

  # NEW INSIGHTS:
  scheduling_delay_ms: 12.5      ← Queueing overhead
  kv_cache_delta_blocks: 15      ← Memory impact
  num_preemptions: 0             ← Cache pressure indicator
  actual_execution_time: 0.350s  ← Execution breakdown
```

## Troubleshooting vLLM Metrics

### Issue: Metrics Endpoint Not Available

```
Error: Failed to fetch metrics from vLLM server
```

**Solution**: Ensure vLLM server is running and `/metrics` endpoint is accessible

```bash
# Check if metrics endpoint works
curl http://localhost:8000/metrics

# If not found, restart server
pkill -f "vllm serve"
sleep 2
vllm serve model_name
```

### Issue: Metrics Are All Zeros

```
kv_cache_usage_pct: 0
num_preemptions: 0
num_requests_running: 0
```

**Possible causes**:
- Prometheus metrics not enabled in vLLM
- Metrics snapshot timing issues
- Server too fast (requests complete before snapshot)

**Solution**:
- Check vLLM startup logs for metrics initialization
- Increase benchmark requests to get stable metrics

### Issue: Preemptions Higher Than Expected

```
num_preemptions: 250 (across 1000 requests)
```

**Indicates**: KV cache pressure

**Solutions**:
1. Reduce max batch size: `--max-num-seqs 128`
2. Enable prefix caching: `--enable-prefix-caching`
3. Increase GPU memory: `--gpu-memory-utilization 0.95`
4. Reduce model size

## Performance Impact of Metrics Collection

Metrics collection has minimal overhead:

- **Per-request overhead**: ~1-2ms (two HTTP requests)
- **Memory overhead**: Negligible (<1MB per 1000 requests)
- **Accuracy**: Metrics may have ±1 second clock skew

For production, consider:
- Sampling metrics (every Nth request)
- Caching metrics (snapshot every second instead of per-request)
- Using vLLM's internal metrics directly

## Advanced: Correlating with Model Behavior

### High KV Delta + High TTFT = Slow Prefill

```
scheduling_delay_ms: 5.0
time_to_first_token: 0.250s    ← HIGH TTFT
kv_cache_delta_blocks: 50      ← HIGH DELTA

→ Indicates: Prefill operation processing large context
→ Action: Enable chunked prefill, reduce batch size
```

### High Scheduling Delay + Running Requests = Queue Backlog

```
scheduling_delay_ms: 85.0                      ← HIGH DELAY
num_requests_running (from metrics_before): 4
num_requests_waiting (from metrics_before): 12 ← LARGE QUEUE

→ Indicates: System overloaded
→ Action: Reduce request rate, scale up resources
```

### Preemptions + Context Swaps = Memory Thrashing

```
num_preemptions: 2
num_context_swap_out: 2
num_context_swap_in: 2

→ Indicates: KV cache not fitting in GPU memory
→ Action: Enable KV quantization, reduce context length, scale up GPU
```

## References

- vLLM Metrics Documentation: https://docs.vllm.ai/en/latest/serving/metrics.html
- Prometheus Format: https://prometheus.io/docs/instrumenting/exposition_formats/
- Related Metrics Guide: [METRICS_GUIDE.md](METRICS_GUIDE.md)
