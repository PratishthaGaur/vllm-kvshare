# Duration Limit Examples - Run Trace for Specific Time Periods

The `--max-duration` parameter lets you run only a portion of the BurstGPT trace based on time duration instead of number of requests.

## Why Use Duration Limits?

- **Faster Testing**: Run only first 15 minutes instead of 121 days of trace
- **Representative Sampling**: Get realistic traffic patterns within your time budget
- **Controlled Experiments**: Compare different vLLM settings on the same time period
- **CI/CD Integration**: Run quick validation without full trace

## Quick Examples

### 15 Minutes of Trace

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/15min_benchmark \
    --max-duration 900  # 15 * 60 seconds
```

### 1 Hour of Trace

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/1hour_benchmark \
    --max-duration 3600  # 1 hour
```

### 30 Minutes of Trace

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/30min_benchmark \
    --max-duration 1800  # 30 * 60 seconds
```

## Time Unit Conversions

| Duration | Seconds | Command |
|----------|---------|---------|
| 5 min | 300 | `--max-duration 300` |
| 10 min | 600 | `--max-duration 600` |
| 15 min | 900 | `--max-duration 900` |
| 20 min | 1200 | `--max-duration 1200` |
| 30 min | 1800 | `--max-duration 1800` |
| 1 hour | 3600 | `--max-duration 3600` |
| 2 hours | 7200 | `--max-duration 7200` |

## Practical Scenarios

### Scenario 1: Quick Smoke Test (5 minutes)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/smoke_test \
    --max-duration 300 \
    --enable-streaming
```

**What you get**: ~5 minutes of realistic traffic patterns, ~2-5 minutes to run

---

### Scenario 2: Full Smoke Test (30 minutes)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/full_smoke_test \
    --max-duration 1800 \
    --enable-streaming
```

**What you get**: 30 minutes of representative traffic, better statistical confidence

---

### Scenario 3: Configuration Comparison

```bash
# Test config A for 15 min
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/config_a \
    --max-duration 900

# Test config B for same 15 min (change server settings between runs)
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/config_b \
    --max-duration 900

# Fair comparison
python benchmarks/analyze_burstgpt_results.py \
    --compare results/config_a results/config_b
```

---

### Scenario 4: Load Testing Different Scales

Run same trace duration with different speed scales:

```bash
# Baseline speed
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/load_1x \
    --max-duration 900 \
    --scale 1.0

# 2x speed
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/load_2x \
    --max-duration 900 \
    --scale 2.0

# 10x speed
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/load_10x \
    --max-duration 900 \
    --scale 10.0

# Compare all
python benchmarks/analyze_burstgpt_results.py \
    --compare results/load_1x results/load_2x results/load_10x \
    --output-format table
```

---

### Scenario 5: CI/CD Pipeline

```bash
#!/bin/bash
set -e

# Quick validation for CI
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model test-model \
    --output-dir ci_results \
    --max-duration 600 \  # 10 minutes
    --timeout 60

# Check success rate
RESULTS=$(cat ci_results/results.json)
SUCCESS_RATE=$(echo $RESULTS | python -c "import sys, json; data=json.load(sys.stdin); print(sum(1 for m in data['metrics'] if m['error'] is None) / len(data['metrics']))")

if (( $(echo "$SUCCESS_RATE >= 0.95" | bc -l) )); then
    echo "✅ Success rate acceptable: $SUCCESS_RATE"
    exit 0
else
    echo "❌ Success rate too low: $SUCCESS_RATE"
    exit 1
fi
```

---

## Combining with Other Parameters

### Using --max-duration with --num-prompts

If you specify both:
- Trace stops at **whichever limit is reached first**
- Use `--num-prompts` to limit by number of requests
- Use `--max-duration` to limit by time

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --max-duration 900 \
    --num-prompts 100  # Whichever comes first
```

### Using --max-duration with --scale

The duration is applied **after** scaling:

```bash
# Scale by 10x, then run for 15 minutes of scaled time
# = 90 minutes of original trace data, replayed in 9 minutes
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --max-duration 900 \
    --scale 10.0
```

---

## Understanding the Output

When using `--max-duration`, the log will show:

```
[INFO] Loaded 523 requests from trace
[INFO] Trace limited to 900.0s (15.0 minutes)
```

This tells you:
- 523 requests fit within the 900-second duration
- Those 523 requests represent the first 15 minutes of production traffic

---

## Performance Tips

### Faster Benchmarking

Start with small durations:

```bash
--max-duration 300  # 5 min - fastest
--max-duration 900  # 15 min - quick
--max-duration 1800 # 30 min - normal
```

### Better Statistics

For publication/production decisions, use longer durations:

```bash
--max-duration 3600  # 1 hour - good confidence
--max-duration 7200  # 2 hours - excellent confidence
```

### Balanced Approach

```bash
--max-duration 1800  # 30 minutes
```

Good balance between:
- Enough data for statistical significance
- Quick execution (typically 15-30 minutes to run)
- Represents realistic production patterns

---

## Troubleshooting

### Issue: Too Few Requests

If you specify a very short duration and get few requests:

```bash
--max-duration 60  # Only 1 minute
# → Might get just 5-10 requests
# → Not enough for meaningful statistics
```

**Solution**: Increase duration to at least 5-10 minutes

---

### Issue: Very Long Execution Time

If you specify very long duration:

```bash
--max-duration 86400  # 24 hours of trace
# → Might contain 100k+ requests
# → Takes hours to run
```

**Solution**: Use reasonable durations (15-60 min) for testing

---

## Practical Guide: Choosing Duration

| Goal | Duration | Execution Time |
|------|----------|-----------------|
| **Quick validation** | 5-10 min (300-600s) | 2-5 min |
| **Basic benchmark** | 15-30 min (900-1800s) | 10-30 min |
| **Production test** | 1-2 hours (3600-7200s) | 1-2 hours |
| **Stress test** | Full trace (combined with `--scale`) | Variable |

---

## Example: Full Benchmark Workflow

```bash
#!/bin/bash

MODEL="llama-2-7b-hf"
TRACE="../data/BurstGPT/data/BurstGPT_1.csv"

echo "=== Starting BurstGPT Benchmarking Workflow ==="

# 1. Quick smoke test
echo "Step 1: Smoke test (5 min)..."
python benchmarks/burstgpt_trace_replay.py \
    --trace-path $TRACE \
    --model $MODEL \
    --output-dir results/1_smoke \
    --max-duration 300

# 2. Extended benchmark
echo "Step 2: Extended test (30 min)..."
python benchmarks/burstgpt_trace_replay.py \
    --trace-path $TRACE \
    --model $MODEL \
    --output-dir results/2_extended \
    --max-duration 1800

# 3. Load test variant
echo "Step 3: Load test (same 30 min, 2x speed)..."
python benchmarks/burstgpt_trace_replay.py \
    --trace-path $TRACE \
    --model $MODEL \
    --output-dir results/3_load \
    --max-duration 1800 \
    --scale 2.0

# 4. Analysis
echo "Step 4: Analyzing results..."
python benchmarks/analyze_burstgpt_results.py \
    --compare results/1_smoke results/2_extended results/3_load \
    --output-format table > benchmark_report.txt

echo "✅ Done! Report saved to benchmark_report.txt"
```

---

## Summary

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `--max-duration` | Limit trace duration in seconds | `--max-duration 900` (15 min) |
| `--num-prompts` | Limit by number of requests | `--num-prompts 100` |
| `--scale` | Speed up/slow down replay | `--scale 2.0` (2x faster) |

**Pro tip**: Combine all three for complete control:

```bash
python benchmarks/burstgpt_trace_replay.py \
    --max-duration 900 \      # 15 min of trace
    --num-prompts 200 \       # But stop at 200 requests (whichever first)
    --scale 2.0               # Replayed 2x faster
```
