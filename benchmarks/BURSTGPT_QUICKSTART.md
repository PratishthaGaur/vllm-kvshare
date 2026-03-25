# BurstGPT Trace Replay - Quick Start Guide

Get started with BurstGPT benchmarking in 5 minutes!

## Prerequisites

- vLLM installed: `pip install vllm`
- Model downloaded or available for auto-download
- Python 3.10+
- BurstGPT trace file

## 5-Minute Setup

### Step 1: Terminal 1 - Start vLLM Server

```bash
cd /Users/pratishthagaur/Downloads/kvshare

vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.8
```

Wait for the message: `INFO:     Uvicorn running on ...`

### Step 2: Terminal 2 - Run Benchmark

```bash
cd /Users/pratishthagaur/Downloads/kvshare/vllm-kvshare

python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/my_first_benchmark \
    --num-prompts 50  # Quick test with 50 requests
```

### Step 3: View Results

```bash
# Check detailed log
tail -f results/my_first_benchmark/benchmark.log

# Or view summary
python benchmarks/analyze_burstgpt_results.py \
    --results-dir results/my_first_benchmark \
    --output-format table
```

That's it! You now have your first benchmark results.

---

## What Happened?

1. ✅ vLLM loaded the model
2. ✅ Benchmark script replayed 50 requests from BurstGPT trace
3. ✅ Requests arrived with exact inter-arrival times
4. ✅ Token counts matched the dataset
5. ✅ Metrics were collected and saved

---

## Understanding the Results

### Key Metrics

```
Requests/sec: 5.2           → How many requests per second
Latency Mean: 0.450s        → Average response time
Time to First Token: 85ms   → How fast first token appears
Success Rate: 98.0%         → Percentage of successful requests
```

### Files Generated

| File | Purpose |
|------|---------|
| `benchmark.log` | Detailed log with all events |
| `results.json` | Complete results in JSON format |
| `results.csv` | Easy-to-analyze CSV file |

---

## Common Tasks

### Task 1: Faster Benchmark (Testing)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/fast_test \
    --num-prompts 20  # Even faster!
```

### Task 2: Production-Like Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/full_benchmark \
    --enable-streaming  # More realistic
    # No --num-prompts = use all requests
```

### Task 3: Compare Two Configurations

First, run baseline:
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/baseline
```

Then, change server config (e.g., disable caching) and run again:
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/without_caching
```

Compare results:
```bash
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline results/without_caching
```

### Task 4: Load Testing (10x Speed)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/load_test \
    --scale 10.0  # 10x faster trace replay
```

---

## Troubleshooting

### ❌ "Connection refused" error

**Problem**: Server not running

**Solution**: Make sure server is running in terminal 1:
```bash
vllm serve meta-llama/Llama-2-7b-hf
```

### ❌ "Model not found" error

**Problem**: Model needs to be downloaded

**Solution**: vLLM will download automatically. First run takes longer.

### ❌ "CUDA out of memory"

**Problem**: GPU memory insufficient

**Solution 1** - Reduce memory usage:
```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --gpu-memory-utilization 0.5  # Instead of 0.8
```

**Solution 2** - Use smaller model:
```bash
vllm serve TinyLlama/TinyLlama-1.1B
```

### ❌ "Requests timing out"

**Problem**: Server too slow or overloaded

**Solution 1** - Increase timeout:
```bash
python benchmarks/burstgpt_trace_replay.py \
    ... \
    --timeout 600  # 10 minutes instead of 5
```

**Solution 2** - Reduce concurrency:
```bash
python benchmarks/burstgpt_trace_replay.py \
    ... \
    --num-prompts 50  # Test with fewer requests
```

---

## Next Steps

### 📚 Learn More

- Full documentation: [BURSTGPT_TRACE_REPLAY.md](BURSTGPT_TRACE_REPLAY.md)
- Configuration examples: [burstgpt_configs.md](burstgpt_configs.md)
- vLLM docs: https://docs.vllm.ai/

### 🚀 Advanced Benchmarking

```bash
# Try the batch script for multiple benchmarks
bash benchmarks/run_burstgpt_benchmark.sh all

# Or run specific benchmarks
bash benchmarks/run_burstgpt_benchmark.sh baseline
bash benchmarks/run_burstgpt_benchmark.sh fast
bash benchmarks/run_burstgpt_benchmark.sh streaming
```

### 📊 Analyze Results

```bash
# Compare multiple results
python benchmarks/analyze_burstgpt_results.py \
    --compare \
        results/baseline \
        results/with_caching \
        results/with_chunked_prefill \
    --output-format table

# Export to CSV
python benchmarks/analyze_burstgpt_results.py \
    --compare results/* \
    --output-format csv > all_results.csv
```

---

## Example Output

```
================================================================================
Benchmark Summary
================================================================================
Total requests: 1000
Successful: 980
Failed: 20
Success rate: 98.00%

Latency Statistics (successful requests only):
  Total latency:
    Mean: 0.486s
    Median: 0.412s
    P99: 1.234s
    P95: 0.856s

  Time to first token:
    Mean: 95.23ms
    Median: 87.45ms
    P99: 234.56ms

Throughput:
  Requests/sec: 4.12

Token Statistics:
  Total input tokens: 485,230
  Total output tokens: 98,450
  Input tokens/sec: 2,047.88
  Output tokens/sec: 415.49

Total benchmark time: 243.52s
================================================================================
```

---

## Tips for Best Results

✅ **Do:**
- Run benchmarks on idle system
- Let server fully warm up (wait 30s after starting)
- Run at least 100 requests for stable metrics
- Compare same configurations multiple times

❌ **Don't:**
- Run other heavy applications while benchmarking
- Compare results from different GPU types
- Use vastly different timeouts for comparisons

---

## Support & Questions

- Check logs: `cat results/*/benchmark.log`
- Look for existing issues: See BurstGPT repository
- Review configurations: [burstgpt_configs.md](burstgpt_configs.md)
- Debug mode: Add Python logging to trace_replay.py

---

**Happy Benchmarking! 🚀**
