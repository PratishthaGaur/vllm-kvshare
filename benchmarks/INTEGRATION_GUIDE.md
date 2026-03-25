# Integration Guide: vLLM Metrics with BurstGPT Benchmark

Step-by-step guide to integrate vLLM metrics collection into your benchmark.

## Files Created

1. **vllm_metrics_collector.py** - Metrics collection module
   - `VLLMMetricsCollector` - Fetches metrics from `/metrics` endpoint
   - `VLLMMetricsSnapshot` - Stores metrics snapshot
   - `RequestVLLMMetrics` - Per-request vLLM metrics

2. **VLLM_METRICS_GUIDE.md** - Detailed metrics documentation

## Quick Integration

### Step 1: Add Metrics Collector to Imports

In `burstgpt_trace_replay.py`, add:

```python
from vllm_metrics_collector import VLLMMetricsCollector, RequestVLLMMetrics
```

### Step 2: Initialize Metrics Collector

In `BurstGPTBenchmark.__init__()`:

```python
self.vllm_metrics_collector = None
if enable_vllm_metrics:
    self.vllm_metrics_collector = VLLMMetricsCollector(base_url)
```

### Step 3: Collect Metrics Before/After Requests

In the `run()` method, before sending a request:

```python
# Snapshot BEFORE request
if self.vllm_metrics_collector:
    metrics_before = await self.vllm_metrics_collector.fetch_metrics()
else:
    metrics_before = None

# Send request...
metrics = await self._send_request(...)

# Snapshot AFTER request
if self.vllm_metrics_collector:
    metrics_after = await self.vllm_metrics_collector.fetch_metrics()
else:
    metrics_after = None

# Store in metrics object
metrics.vllm_metrics_before = metrics_before
metrics.vllm_metrics_after = metrics_after
```

### Step 4: Add CLI Parameter

```python
parser.add_argument(
    "--collect-vllm-metrics",
    action="store_true",
    help="Collect detailed vLLM server metrics (requires /metrics endpoint)"
)
```

### Step 5: Run with Metrics

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/with_metrics \
    --collect-vllm-metrics
```

## What Gets Recorded

### Per-Request (in results.json)

```json
{
  "request_id": 0,

  // Existing metrics
  "timestamp": 5.23,
  "request_tokens": 472,
  "total_latency": 0.384,

  // NEW vLLM metrics
  "scheduling_delay_ms": 12.5,
  "kv_cache_delta_blocks": 15,
  "num_preemptions": 0,
  "tokens_generated_during_request": 18,

  // Detailed snapshots
  "vllm_metrics_before": {
    "timestamp": 1711094415.234,
    "kv_cache_usage_pct": 45.2,
    "kv_cache_used_blocks": 2245,
    "num_requests_running": 3,
    "num_preemptions": 12,
    ...
  },
  "vllm_metrics_after": {
    "timestamp": 1711094415.624,
    "kv_cache_usage_pct": 47.8,
    "kv_cache_used_blocks": 2260,
    "num_requests_running": 2,
    "num_preemptions": 12,
    ...
  }
}
```

### Aggregate Statistics

Added to logs:

```
KV Cache Statistics:
  Peak usage: 75.3%
  Avg delta per request: 18 blocks
  P99 delta: 45 blocks

Scheduling Statistics:
  Avg scheduling delay: 15.4ms
  P99 scheduling delay: 87.5ms

Preemption Statistics:
  Total preemptions: 23
  Requests affected: 18 (1.8%)
```

## Example Analysis

### View KV Cache Impact

```python
import json
import numpy as np

with open('results/with_metrics/results.json') as f:
    data = json.load(f)

metrics = data['metrics']
successful = [m for m in metrics if not m.get('error')]

kv_deltas = [m['kv_cache_delta_blocks'] for m in successful
             if m.get('kv_cache_delta_blocks')]

print(f"KV Cache Block Changes:")
print(f"  Mean: {np.mean(kv_deltas):.1f}")
print(f"  Median: {np.median(kv_deltas):.1f}")
print(f"  P99: {np.percentile(kv_deltas, 99):.1f}")
print(f"  Max: {max(kv_deltas)}")
```

### View Scheduling Delays

```python
scheduling_delays = [m['scheduling_delay_ms'] for m in successful
                     if m.get('scheduling_delay_ms')]

print(f"Scheduling Delays (ms):")
print(f"  Mean: {np.mean(scheduling_delays):.2f}")
print(f"  P95: {np.percentile(scheduling_delays, 95):.2f}")
print(f"  P99: {np.percentile(scheduling_delays, 99):.2f}")
```

### Compare Preemption Impact

```python
preempted = [m for m in successful if m.get('num_preemptions', 0) > 0]
not_preempted = [m for m in successful if m.get('num_preemptions', 0) == 0]

preempted_latency = np.mean([m['total_latency'] for m in preempted])
normal_latency = np.mean([m['total_latency'] for m in not_preempted])

print(f"Preemption Impact:")
print(f"  Preempted requests latency: {preempted_latency:.3f}s")
print(f"  Normal requests latency: {normal_latency:.3f}s")
print(f"  Overhead: {(preempted_latency/normal_latency - 1)*100:.1f}%")
```

## Server Configuration for Metrics

### Enable Prometheus Metrics

vLLM automatically exposes metrics on the `/metrics` endpoint:

```bash
# Metrics are available at:
curl http://localhost:8000/metrics

# Check if working:
curl http://localhost:8000/metrics | head -20
```

### View Available Metrics

```bash
# See all metrics being collected
curl http://localhost:8000/metrics | grep "vllm:"

# Example output:
# vllm:gpu_cache_usage_perc{model_name="..."} 45.2
# vllm:num_preemptions_total{model_name="..."} 12
# vllm:num_requests_running{model_name="..."} 3
```

## Overhead Analysis

### Performance Impact

```
Metrics Collection Overhead:
├─ Per-request overhead: 1-2ms (2 HTTP requests)
├─ Memory overhead: <1MB per 1000 requests
└─ Accuracy: ±0.5-1 second clock skew
```

### When to Use

✅ **Use metrics collection when:**
- Investigating performance issues
- Comparing configurations
- Understanding scheduling behavior
- Analyzing KV cache pressure

❌ **Skip metrics collection when:**
- Running very frequent benchmarks (> 100/day)
- Network latency is very high (> 100ms to server)
- Benchmark must complete very quickly

### Optimization

For production, consider:

```python
# Sample every Nth request
if request_id % 10 == 0:  # Every 10th request
    metrics_before = await self.vllm_metrics_collector.fetch_metrics()
```

## Troubleshooting

### Error: "Cannot connect to /metrics endpoint"

```bash
# Check server is running
curl http://localhost:8000/v1/models

# Check metrics endpoint specifically
curl http://localhost:8000/metrics
```

### Metrics all zero

- Server might be too fast (complete before snapshot)
- Increase number of requests: `--num-prompts 1000`
- Check if metrics are initialized in server logs

### Missing specific metrics

Not all metrics are available in all vLLM versions:
- Check vLLM version: `python -c "import vllm; print(vllm.__version__)"`
- Some metrics require additional flags (e.g., `--enable-mfu-metrics`)

## Advanced Usage

### Store metrics separately

```python
# Save just vLLM metrics to separate file
vllm_metrics_only = {
    'config': data['benchmark_config'],
    'vllm_metrics': [
        {
            'request_id': m['request_id'],
            'vllm_before': m['vllm_metrics_before'],
            'vllm_after': m['vllm_metrics_after'],
        }
        for m in data['metrics']
    ]
}

with open('vllm_metrics.json', 'w') as f:
    json.dump(vllm_metrics_only, f)
```

### Real-time monitoring

```python
# Show metrics as benchmark runs
async def monitor_metrics(collector):
    while True:
        metrics = await collector.fetch_metrics()
        print(f"KV Usage: {metrics.kv_cache_usage_pct:.1f}% | "
              f"Running: {metrics.num_requests_running} | "
              f"Waiting: {metrics.num_requests_waiting}")
        await asyncio.sleep(1)
```

## Comparison Scripts

### Compare with/without metrics

```bash
# Run baseline
python burstgpt_trace_replay.py \
    --model llama-2-7b-hf \
    --output-dir results/baseline

# Run with metrics
python burstgpt_trace_replay.py \
    --model llama-2-7b-hf \
    --output-dir results/with_metrics \
    --collect-vllm-metrics

# Compare latency overhead
python -c "
import json
baseline = json.load(open('results/baseline/results.json'))
with_metrics = json.load(open('results/with_metrics/results.json'))

b_latency = sum(m['total_latency'] for m in baseline['metrics']) / len(baseline['metrics'])
w_latency = sum(m['total_latency'] for m in with_metrics['metrics']) / len(with_metrics['metrics'])

print(f'Latency increase from metrics: {(w_latency/b_latency - 1)*100:.1f}%')
"
```

## Next Steps

1. ✅ Integrate `vllm_metrics_collector.py` into your benchmark
2. ✅ Add `--collect-vllm-metrics` CLI parameter
3. ✅ Store metrics in results JSON
4. ✅ Analyze using examples above
5. ✅ Compare different configurations with vLLM metrics

## References

- [VLLM_METRICS_GUIDE.md](VLLM_METRICS_GUIDE.md) - Detailed metrics explanation
- [METRICS_GUIDE.md](METRICS_GUIDE.md) - General metrics documentation
- vLLM Metrics Docs: https://docs.vllm.ai/en/latest/serving/metrics.html
