# BurstGPT Benchmark Configuration Examples

This document provides ready-to-use configuration examples for different benchmarking scenarios.

## Table of Contents

1. [Server Configurations](#server-configurations)
2. [Benchmark Configurations](#benchmark-configurations)
3. [Comparative Studies](#comparative-studies)
4. [Load Testing](#load-testing)
5. [Production Analysis](#production-analysis)

---

## Server Configurations

### 1. Minimal Configuration (CPU-friendly testing)

```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --gpu-memory-utilization 0.5
```

**When to use**: Quick testing, limited GPU memory, or CI/CD pipelines

---

### 2. Balanced Configuration (Recommended for most benchmarks)

```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.8 \
    --max-num-batched-tokens 4096
```

**Benefits**:
- Prefix caching reduces latency for repeated contexts
- Balanced memory usage
- Good throughput for typical workloads

**When to use**: Standard benchmarking, production testing

---

### 3. High-Performance Configuration

```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.9 \
    --max-num-batched-tokens 8192 \
    --tensor-parallel-size 1
```

**Benefits**:
- Chunked prefill for better batching
- Maximum memory utilization
- Optimized for throughput

**When to use**: High-concurrency scenarios, production deployments

---

### 4. Multi-GPU Configuration (Large models)

```bash
vllm serve meta-llama/Llama-2-70b-hf \
    --tensor-parallel-size 4 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.9
```

**When to use**: Large models like 70B, 13B models

---

### 5. Speculative Decoding Configuration (Faster inference)

```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --speculative-model meta-llama/Llama-2-7b-hf \
    --num-speculative-tokens 5 \
    --use-v2-block-manager
```

**Benefits**:
- Faster token generation through speculation
- Maintains token accuracy

**When to use**: Latency-sensitive applications

---

## Benchmark Configurations

### 1. Baseline Benchmark (No optimizations)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/baseline \
    --scale 1.0 \
    --temperature 0.0
```

**Output**: Baseline metrics for future comparisons

---

### 2. Streaming Mode Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/streaming \
    --enable-streaming
```

**Measures**: Accurate time-to-first-token latency

---

### 3. Quick Validation (100 requests only)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/quick_test \
    --num-prompts 100
```

**Use for**: Quick smoke tests, debugging

---

### 4. Load Testing (100x faster)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/load_test_100x \
    --scale 100.0 \
    --enable-streaming
```

**Measures**: System behavior under high concurrency

---

### 5. Fixed Request Rate Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/fixed_rate_10qps \
    --request-rate 10.0 \
    --enable-streaming
```

**Use for**: Testing at specific request rates

---

## Comparative Studies

### Study 1: Impact of Prefix Caching

```bash
# Step 1: Baseline (without prefix caching)
vllm serve meta-llama/Llama-2-7b-hf \
    --gpu-memory-utilization 0.8

# In another terminal:
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/baseline_no_caching \
    --enable-streaming

# Step 2: With prefix caching
# Kill the server and restart with:
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.8

python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/baseline_with_caching \
    --enable-streaming

# Step 3: Compare
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline_no_caching results/baseline_with_caching
```

---

### Study 2: Model Comparison

```bash
#!/bin/bash

TRACE="data/BurstGPT/data/BurstGPT_1.csv"
MODELS=("llama-2-7b-hf" "mistral-7b" "neural-chat-7b-v3-1")

for MODEL in "${MODELS[@]}"; do
    echo "Testing $MODEL..."

    # Kill previous server
    pkill -f "vllm serve"
    sleep 2

    # Start server with model
    vllm serve $MODEL \
        --enable-prefix-caching \
        --gpu-memory-utilization 0.8 &
    sleep 10

    # Run benchmark
    python benchmarks/burstgpt_trace_replay.py \
        --trace-path $TRACE \
        --model $MODEL \
        --output-dir results/model_comparison_$MODEL \
        --enable-streaming
done

# Compare all results
python benchmarks/analyze_burstgpt_results.py \
    --compare results/model_comparison_* \
    --output-format table
```

---

### Study 3: Batch Size Impact

```bash
#!/bin/bash

TRACE="data/BurstGPT/data/BurstGPT_1.csv"
BATCH_SIZES=(2048 4096 8192)

for BATCH in "${BATCH_SIZES[@]}"; do
    echo "Testing batch size $BATCH..."

    pkill -f "vllm serve"
    sleep 2

    vllm serve meta-llama/Llama-2-7b-hf \
        --enable-prefix-caching \
        --max-num-batched-tokens $BATCH \
        --gpu-memory-utilization 0.8 &
    sleep 5

    python benchmarks/burstgpt_trace_replay.py \
        --trace-path $TRACE \
        --model llama-2-7b-hf \
        --output-dir results/batch_$BATCH \
        --enable-streaming
done
```

---

## Load Testing

### Scenario 1: Peak Hour Simulation (10x normal)

```bash
# Server with high-performance config
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.9 \
    --max-num-batched-tokens 8192

# Benchmark at 10x speed
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/peak_hour_10x \
    --scale 10.0 \
    --enable-streaming
```

---

### Scenario 2: Stress Testing (100x normal)

```bash
# High-performance server config
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.95 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 256

# Stress test at 100x speed
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/stress_test_100x \
    --scale 100.0 \
    --enable-streaming \
    --timeout 600
```

---

### Scenario 3: Sustained Load (Fixed 20 requests/sec)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/sustained_20qps \
    --request-rate 20.0 \
    --enable-streaming
```

---

## Production Analysis

### Production Deployment Benchmark

```bash
# Production-like configuration
vllm serve meta-llama/Llama-2-7b-hf \
    --tensor-parallel-size 2 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.85 \
    --max-num-batched-tokens 4096 \
    --max-num-seqs 128

# Realistic traffic replay
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/production_deployment \
    --scale 1.0 \
    --enable-streaming \
    --temperature 0.7
```

---

## Result Analysis

### Compare multiple benchmarks

```bash
python benchmarks/analyze_burstgpt_results.py \
    --compare \
        results/baseline \
        results/with_caching \
        results/with_chunked_prefill \
    --output-format table
```

### Export as CSV for Excel/Sheets

```bash
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline results/optimized \
    --output-format csv > comparison.csv
```

---

## Tips for Better Benchmarking

1. **Warm-up runs**: Run at least one quick benchmark before real testing to warm up the GPU
2. **Multiple runs**: Run the same benchmark 3-5 times and average results
3. **Stable environment**: Close other applications to reduce system variance
4. **Pin CPU cores**: Use `taskset` for more consistent results
5. **Monitor GPU**: Use `nvidia-smi` in another terminal to monitor GPU utilization
6. **Log storage**: Ensure the output directory is on a fast disk

---

## Troubleshooting

### Issue: High variance in results

**Solution**:
- Increase `--num-prompts` to run longer benchmarks
- Run multiple times and average
- Close other applications

### Issue: Server crashes under load

**Solution**:
- Reduce `--gpu-memory-utilization` to 0.7
- Use smaller model
- Increase `--timeout`

### Issue: Token count mismatch

**Solution**:
- Check if tokenizer is loaded correctly
- Verify model matches between server and benchmark script

---

## References

- BurstGPT Paper: https://github.com/mitigation/burstgpt
- vLLM Documentation: https://docs.vllm.ai/
- vLLM Benchmarking: https://docs.vllm.ai/en/latest/benchmark/
