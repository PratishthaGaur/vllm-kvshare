# BurstGPT Benchmarking Suite - Complete Summary

Comprehensive online serving benchmarking tools for vLLM with BurstGPT traces.

## 📦 Complete Package Contents

### Core Benchmarking Scripts

| File | Purpose | Status |
|------|---------|--------|
| `burstgpt_trace_replay.py` | Main benchmark script | ✅ Complete |
| `vllm_metrics_collector.py` | vLLM metrics collection | ✅ New |
| `analyze_burstgpt_results.py` | Results analysis tool | ✅ Complete |
| `run_burstgpt_benchmark.sh` | Convenient bash wrapper | ✅ Complete |

### Documentation

| File | Content | Purpose |
|------|---------|---------|
| **BURSTGPT_QUICKSTART.md** | 5-minute setup guide | 👈 **Start here** |
| **BURSTGPT_TRACE_REPLAY.md** | Complete documentation | Reference |
| **METRICS_GUIDE.md** | All collected metrics explained | Metrics reference |
| **METRICS_QUICK_REFERENCE.md** | Quick metrics lookup | Cheat sheet |
| **DATA_STRUCTURE.txt** | Visual data flow diagram | Architecture |
| **burstgpt_configs.md** | Configuration examples | Server setup |
| **DURATION_LIMIT_EXAMPLES.md** | Duration control guide | Feature guide |
| **VLLM_METRICS_GUIDE.md** | vLLM metrics details | Metrics details |
| **INTEGRATION_GUIDE.md** | How to integrate metrics | Implementation |
| **SUMMARY.md** | This file | Overview |

## 🎯 Key Features

### ✅ Implemented

- [x] Trace replay with exact inter-arrival times
- [x] Token count matching from dataset
- [x] Comprehensive latency metrics (mean, median, P95, P99)
- [x] Throughput metrics (requests/sec, tokens/sec)
- [x] Time-to-first-token measurement
- [x] Error tracking and recovery
- [x] Configurable duration limits (`--max-duration`)
- [x] Configurable request count limits (`--num-prompts`)
- [x] Configurable replay speed (`--scale`)
- [x] Results export (JSON, CSV, logs)
- [x] Comparison analysis tool
- [x] Batch benchmark wrapper
- [x] Streaming and non-streaming modes

### 🆕 vLLM-Specific Metrics (New!)

- [x] KV cache metrics collection
  - Cache usage percentage
  - Block allocation/deallocation tracking
  - KV cache deltas per-request
- [x] Scheduling delay metrics
  - Queue wait time
  - Scheduling overhead
  - Request state tracking
- [x] Preemption tracking
  - Preemption counts
  - Context swap events
  - Preemption impact on latency
- [x] Engine metrics
  - Running requests
  - Waiting queue depth
  - Swapped context count
- [x] Metrics snapshots before/after requests
- [x] Delta calculations for counter-based metrics

## 📊 What Gets Recorded

### Per-Request Metrics

```
For each of ~1000 requests:

Basic:
  ├─ request_id: 0
  ├─ timestamp: 5.23s
  ├─ request_tokens: 472
  └─ expected_output_tokens: 18

Latency:
  ├─ time_to_first_token: 0.142s
  ├─ total_latency: 0.384s
  └─ error: null

Actual Results:
  ├─ actual_input_tokens: 472
  ├─ actual_output_tokens: 18
  └─ matching: ✓

[NEW] vLLM Metrics:
  ├─ scheduling_delay_ms: 12.5
  ├─ kv_cache_delta_blocks: 15
  ├─ num_preemptions: 0
  ├─ tokens_generated_during_request: 18
  └─ actual_execution_time: 0.350s
```

### Aggregate Statistics

```
Request Counts:
  ├─ Total: 980
  ├─ Successful: 960 (98%)
  └─ Failed: 20 (2%)

Latency:
  ├─ Mean: 0.486s
  ├─ Median: 0.412s
  ├─ P95: 0.856s
  └─ P99: 1.234s

TTFT (Time-to-First-Token):
  ├─ Mean: 95.23ms
  ├─ Median: 87.45ms
  ├─ P95: 234.56ms
  └─ P99: 456.78ms

Throughput:
  ├─ Requests/sec: 4.12
  ├─ Input tokens/sec: 2,047.88
  └─ Output tokens/sec: 415.49

[NEW] KV Cache:
  ├─ Peak usage: 75.3%
  ├─ Avg delta: 18 blocks
  └─ Max delta: 45 blocks

[NEW] Scheduling:
  ├─ Avg delay: 15.4ms
  ├─ P99 delay: 87.5ms
  └─ Max delay: 150.2ms

[NEW] Preemptions:
  ├─ Total: 23
  ├─ Affected requests: 18
  └─ Avg per request: 0.023
```

## 🚀 Quick Start (5 Minutes)

### 1. Terminal 1: Start Server
```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.8
```

### 2. Terminal 2: Run Benchmark
```bash
cd /Users/pratishthagaur/Downloads/kvshare/vllm-kvshare

python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/my_benchmark \
    --max-duration 900 \              # 15 minutes
    --collect-vllm-metrics            # NEW: Collect vLLM metrics
```

### 3. View Results
```bash
# Summary in console
tail -50 results/my_benchmark/benchmark.log

# Detailed analysis
python benchmarks/analyze_burstgpt_results.py \
    --results-dir results/my_benchmark \
    --output-format table

# KV cache analysis
python -c "
import json, numpy as np
with open('results/my_benchmark/results.json') as f:
    data = json.load(f)
metrics = [m for m in data['metrics'] if m.get('kv_cache_delta_blocks')]
print(f'KV delta: mean={np.mean([m[\"kv_cache_delta_blocks\"] for m in metrics]):.1f} blocks')
"
```

## 📈 Typical Output Files

```
results/my_benchmark/
├── benchmark.log                    # Detailed log with all events
├── results.json                     # Complete data (use this!)
├── results.csv                      # Spreadsheet format
└── [generated metrics snapshots]
```

### results.json Structure
```json
{
  "benchmark_config": {
    "trace_path": "...",
    "model": "llama-2-7b-hf",
    "base_url": "http://localhost:8000",
    "collect_vllm_metrics": true,    // NEW
    "timestamp": "2024-03-22T10:30:15.234567"
  },
  "summary": {
    "total_requests": 980,
    "successful_requests": 960,
    "failed_requests": 20
  },
  "metrics": [
    {
      "request_id": 0,
      // ... all per-request metrics
      "scheduling_delay_ms": 12.5,           // NEW
      "kv_cache_delta_blocks": 15,           // NEW
      "num_preemptions": 0,                  // NEW
      "vllm_metrics_before": {...},          // NEW
      "vllm_metrics_after": {...}            // NEW
    }
    // ... 979 more requests
  ]
}
```

## 💡 Usage Patterns

### Pattern 1: Quick Smoke Test
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/smoke_test \
    --max-duration 300              # 5 minutes
```

### Pattern 2: Full Benchmark
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/full \
    --collect-vllm-metrics          # Include vLLM metrics
```

### Pattern 3: Load Test
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/load_test \
    --scale 10.0                    # 10x faster
    --collect-vllm-metrics
```

### Pattern 4: Configuration Comparison
```bash
# Run baseline
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/baseline \
    --max-duration 1800 \
    --collect-vllm-metrics

# (Change server config, restart server)

# Run optimized
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/optimized \
    --max-duration 1800 \
    --collect-vllm-metrics

# Compare
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline results/optimized
```

## 🔍 Interpreting Key Metrics

### Latency Percentiles
- **P99**: Worst 1% of requests (SLA critical)
- **P95**: Worst 5% of requests
- **Median**: Middle request
- **Mean**: Average (affected by outliers)

### Time-to-First-Token
- **<100ms**: Feels instant ✅
- **100-500ms**: Good for chat ✓
- **>500ms**: Noticeable delay ⚠️

### KV Cache Delta
- Shows memory allocation during request
- Large deltas = long context or slow prefill
- If exceeds free blocks → preemption needed

### Scheduling Delay
- Queue wait time before execution
- High delay = system overloaded
- Indicates request contention

### Preemptions
- Count = number of times preempted
- Each preemption adds 20-100ms
- High count = KV cache pressure

## 🛠️ Tools Provided

| Tool | Purpose | Command |
|------|---------|---------|
| **burstgpt_trace_replay.py** | Run benchmark | `python burstgpt_trace_replay.py --...` |
| **analyze_burstgpt_results.py** | Analyze results | `python analyze_burstgpt_results.py --...` |
| **run_burstgpt_benchmark.sh** | Convenient wrapper | `bash run_burstgpt_benchmark.sh baseline` |
| **vllm_metrics_collector.py** | Metrics collection | (imported internally) |

## 📚 Documentation Map

```
Getting Started:
  └─ BURSTGPT_QUICKSTART.md ← Start here!

Understanding Metrics:
  ├─ METRICS_GUIDE.md (detailed)
  ├─ METRICS_QUICK_REFERENCE.md (quick lookup)
  ├─ VLLM_METRICS_GUIDE.md (vLLM-specific)
  └─ DATA_STRUCTURE.txt (visual architecture)

Using the Tools:
  ├─ BURSTGPT_TRACE_REPLAY.md (full documentation)
  ├─ burstgpt_configs.md (server configuration)
  ├─ DURATION_LIMIT_EXAMPLES.md (duration control)
  └─ INTEGRATION_GUIDE.md (adding to your code)

Reference:
  └─ SUMMARY.md (this file)
```

## ✨ What's New in This Version

### vLLM Metrics Integration

```python
# Now automatically collected when --collect-vllm-metrics is passed:
per_request_metrics = {
    "scheduling_delay_ms": 12.5,           # How long in queue
    "kv_cache_delta_blocks": 15,           # Memory allocation
    "num_preemptions": 0,                  # Preemption events
    "tokens_generated_during_request": 18, # Actual generation
    "actual_execution_time": 0.350,        # Execution breakdown

    # Detailed snapshots
    "vllm_metrics_before": {...},          # System state before
    "vllm_metrics_after": {...}            # System state after
}
```

### Duration Limiting

```bash
# Run only first 15 minutes of 121-day trace
--max-duration 900
```

### Enhanced Analysis

All existing tools automatically handle the new metrics:
```bash
python analyze_burstgpt_results.py --results-dir results/my_benchmark
# Automatically includes vLLM metrics in output
```

## 🔗 Integration Checklist

- [x] Core benchmark script ready
- [x] Metrics collector module ready
- [x] Analysis tools ready
- [x] Documentation complete
- [x] Duration limiting implemented
- [x] vLLM metrics collection implemented
- [x] Example configurations provided
- [x] Quick start guide ready

## 📝 Configuration Examples

See [burstgpt_configs.md](burstgpt_configs.md) for:
- ✅ Minimal setup
- ✅ Balanced configuration (recommended)
- ✅ High-performance setup
- ✅ Multi-GPU setup
- ✅ Speculative decoding
- ✅ Comparative studies
- ✅ Load testing scenarios
- ✅ Production analysis

## 🎓 Learning Path

1. **First**: Read [BURSTGPT_QUICKSTART.md](BURSTGPT_QUICKSTART.md)
2. **Then**: Run first benchmark (5 min)
3. **Next**: Check [METRICS_QUICK_REFERENCE.md](METRICS_QUICK_REFERENCE.md)
4. **Explore**: Try different configurations from [burstgpt_configs.md](burstgpt_configs.md)
5. **Deep dive**: Read [VLLM_METRICS_GUIDE.md](VLLM_METRICS_GUIDE.md)
6. **Advanced**: Integrate into your code using [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)

## 🚀 Next Steps

```bash
# 1. Start vLLM server
vllm serve meta-llama/Llama-2-7b-hf --enable-prefix-caching

# 2. Run benchmark
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/my_first_benchmark \
    --max-duration 900 \
    --collect-vllm-metrics

# 3. Analyze results
python benchmarks/analyze_burstgpt_results.py \
    --results-dir results/my_first_benchmark
```

That's it! You now have comprehensive benchmarking with vLLM metrics. 🎉

## 📞 Support

- **Quick questions**: Check [METRICS_QUICK_REFERENCE.md](METRICS_QUICK_REFERENCE.md)
- **Understanding metrics**: Read [VLLM_METRICS_GUIDE.md](VLLM_METRICS_GUIDE.md)
- **Configuration help**: See [burstgpt_configs.md](burstgpt_configs.md)
- **Integration help**: Read [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
- **Troubleshooting**: Check [BURSTGPT_TRACE_REPLAY.md](BURSTGPT_TRACE_REPLAY.md)

---

**Version**: 2.0 (with vLLM metrics)
**Status**: ✅ Ready for production use
**Last Updated**: March 22, 2024
