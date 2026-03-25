# BurstGPT Trace Replay Benchmarking Suite

Professional-grade benchmarking tools for vLLM online serving using the BurstGPT dataset traces.

## Overview

This suite provides everything needed to:

✅ **Replay** BurstGPT traces in real-time against a vLLM server
✅ **Control** vLLM settings like prefix caching, GPU memory, etc.
✅ **Match** exact input/output token counts from the dataset
✅ **Measure** latency, throughput, and other key metrics
✅ **Compare** different configurations systematically
✅ **Scale** trace replay up or down for different load levels

## Files Included

### Main Benchmark Script

**[burstgpt_trace_replay.py](burstgpt_trace_replay.py)** (Main tool)
- Complete online serving benchmark for BurstGPT traces
- Async request handling for realistic concurrent scenarios
- Comprehensive metrics collection (latency, throughput, tokens/sec)
- Robust error handling with detailed logging
- Configurable model, vLLM settings, and replay speed

**Key features:**
- Exact inter-arrival time replay from trace
- Automatic prompt generation to match token counts
- Streaming and non-streaming modes
- Timeout and error tracking
- JSON and CSV output formats

### Helper Scripts

**[run_burstgpt_benchmark.sh](run_burstgpt_benchmark.sh)** (Convenience wrapper)
- Easy-to-use bash script for common benchmarking tasks
- Pre-configured benchmark scenarios
- Multi-benchmark comparison support
- Automatic model detection from server

**Usage:**
```bash
bash benchmarks/run_burstgpt_benchmark.sh baseline
bash benchmarks/run_burstgpt_benchmark.sh all
```

**[analyze_burstgpt_results.py](analyze_burstgpt_results.py)** (Results analysis)
- Compute detailed statistics from benchmark results
- Compare multiple benchmark runs
- Export results to table or CSV format
- Speedup calculations between baselines

**Usage:**
```bash
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline results/optimized \
    --output-format table
```

### Documentation

| File | Purpose |
|------|---------|
| [BURSTGPT_QUICKSTART.md](BURSTGPT_QUICKSTART.md) | **Start here!** 5-minute setup guide |
| [BURSTGPT_TRACE_REPLAY.md](BURSTGPT_TRACE_REPLAY.md) | Comprehensive documentation and examples |
| [burstgpt_configs.md](burstgpt_configs.md) | Configuration examples for different scenarios |
| [BURSTGPT_README.md](BURSTGPT_README.md) | This file |

## Quick Start

### 1. Start vLLM Server

```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.8
```

### 2. Run Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path ../data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/my_benchmark \
    --enable-streaming
```

### 3. View Results

```bash
python benchmarks/analyze_burstgpt_results.py \
    --results-dir results/my_benchmark \
    --output-format table
```

**See [BURSTGPT_QUICKSTART.md](BURSTGPT_QUICKSTART.md) for detailed walkthrough!**

## Key Differences from BurstGPT Example

The built-in BurstGPT example (`data/BurstGPT/example/`) is designed for profiling and tracing. Our benchmarking suite improves upon it:

| Feature | Example Script | Our Suite |
|---------|----------------|-----------|
| **Inter-arrival timing** | ✅ Supported | ✅ Exact trace replay |
| **Token matching** | ⚠️ Approximate | ✅ Exact matching |
| **Error handling** | Basic | ✅ Robust with recovery |
| **Configuration** | Limited | ✅ Highly configurable |
| **Metrics** | Basic logging | ✅ Comprehensive stats |
| **Comparison** | N/A | ✅ Built-in analysis |
| **Documentation** | Minimal | ✅ Extensive |
| **Ease of use** | Code-heavy | ✅ CLI-based |
| **Scaling** | Fixed trace | ✅ Adjustable speed |
| **Result export** | JSON only | ✅ JSON + CSV |

### When to Use Each

**Use the built-in example if:**
- You need low-level access to server profiling
- You want to extend with custom profiling logic
- You're debugging specific server behaviors

**Use our benchmarking suite if:**
- You want production-grade benchmarking
- You need to compare configurations
- You want easy reporting and analysis
- You need reproducible results

## Core Functionality

### 1. Trace Replay

The benchmark reads BurstGPT CSV traces with:
- **Timestamp**: Request arrival time (inter-arrival intervals)
- **Request tokens**: Input prompt size
- **Response tokens**: Expected output size
- **Model type**: ChatGPT or GPT-4 (informational)

Replays requests at the exact same arrival rate, maintaining concurrency patterns from production traffic.

### 2. Token Management

Automatically generates prompts with exact token counts:
- Uses model's tokenizer for accurate counting
- Pads or truncates to match dataset specifications
- Falls back to mock tokenizer if transformers unavailable
- Ensures reproducible token counts across runs

### 3. Concurrent Requests

Handles request scheduling with:
- Precise sleep calculations based on trace inter-arrivals
- Async request handling for realistic concurrency
- Configurable timeouts per request
- Comprehensive error tracking

### 4. Metrics Collection

Collects per-request metrics:
- **Request ID**: For tracing specific requests
- **Timestamp**: When request was scheduled
- **Input tokens**: Actual tokens sent
- **Output tokens**: Tokens received
- **Time-to-first-token**: Prefill latency
- **Total latency**: End-to-end response time
- **Errors**: Any failures with details

Computes aggregate statistics:
- Mean, median, P95, P99 latencies
- Requests per second
- Tokens per second (input and output)
- Success rate and error breakdown

### 5. Results Export

Generates three output formats:
- **benchmark.log**: Detailed timestamped events
- **results.json**: Complete metrics in JSON
- **results.csv**: Spreadsheet-friendly format

## Configuration Options

### Model & Server

```bash
--model llama-2-7b-hf          # Model name
--base-url http://localhost:8000  # Server URL
```

### Trace Control

```bash
--trace-path data/BurstGPT/data/BurstGPT_1.csv  # Dataset path
--scale 1.0                    # Replay speed (1.0 = real-time)
--num-prompts 100              # Limit requests
--request-rate 5.0             # Override with fixed rate
```

### Request Options

```bash
--enable-streaming             # Use streaming responses
--timeout 300                  # Request timeout (seconds)
--temperature 0.0              # Sampling temperature
```

### Output

```bash
--output-dir results/my_benchmark  # Results directory
```

## Usage Patterns

### Pattern 1: Baseline + Comparison

```bash
# Run baseline
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/baseline

# Change server config, run again
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model llama-2-7b-hf \
    --output-dir results/optimized

# Compare
python benchmarks/analyze_burstgpt_results.py \
    --compare results/baseline results/optimized
```

### Pattern 2: Parameter Sweep

```bash
for BATCH in 2048 4096 8192; do
    vllm serve model --max-num-batched-tokens $BATCH &
    sleep 5

    python benchmarks/burstgpt_trace_replay.py \
        --model llama-2-7b-hf \
        --output-dir results/batch_$BATCH \
        ...

    pkill -f "vllm serve"
done
```

### Pattern 3: Load Testing

```bash
# Quick validation
--num-prompts 50

# Normal benchmark
# (use all requests from trace)

# Heavy load test
--scale 100.0

# Sustained load
--request-rate 20.0
```

## Performance Considerations

### For Faster Benchmarking

1. Use `--num-prompts` to limit requests
2. Use `--scale` to speed up replay
3. Test on smaller models first

### For Accurate Results

1. Use full trace (no `--num-prompts` limit)
2. Use `--scale 1.0` (real-time replay)
3. Use `--enable-streaming` (realistic)
4. Run multiple times and average
5. Close other applications

### For Load Testing

1. Use `--scale` > 1.0 for higher concurrency
2. Monitor GPU/CPU usage with `nvidia-smi`
3. Increase timeout if needed
4. Check error rates and recovery

## Common Scenarios

### Scenario 1: CI/CD Integration

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model test-model \
    --output-dir ci_results \
    --num-prompts 100 \
    --timeout 60 \
    && python benchmarks/analyze_burstgpt_results.py \
        --results-dir ci_results
```

### Scenario 2: Production Testing

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model production-model \
    --output-dir prod_results \
    --enable-streaming \
    --temperature 0.7
```

### Scenario 3: Development

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --model test-model \
    --output-dir dev_results \
    --num-prompts 20 \
    --scale 10.0
```

## Troubleshooting

### Connection Issues
```bash
# Verify server is running
curl http://localhost:8000/v1/models

# Check server logs
tail -f server_logs.txt
```

### Token Count Mismatches
```bash
# Ensure tokenizer matches model
# Check model name parameter matches server model
```

### Performance Issues
```bash
# Monitor GPU
nvidia-smi

# Check system resources
top

# Try smaller model or fewer concurrent requests
```

## File Structure

```
vllm-kvshare/benchmarks/
├── burstgpt_trace_replay.py         # Main benchmark script
├── run_burstgpt_benchmark.sh         # Bash convenience wrapper
├── analyze_burstgpt_results.py       # Results analysis
├── BURSTGPT_QUICKSTART.md           # Quick start guide
├── BURSTGPT_TRACE_REPLAY.md         # Full documentation
├── burstgpt_configs.md               # Configuration examples
└── BURSTGPT_README.md               # This file
```

## License

Apache License 2.0 - Same as vLLM

## Citation

If you use this benchmark suite in research, cite:

```bibtex
@software{kvshare_burstgpt_benchmark,
  title={BurstGPT Trace Replay Benchmarking Suite for vLLM},
  author={Gaur, Pratishtha},
  year={2024},
  url={https://github.com/...}
}
```

Also cite the original BurstGPT paper and vLLM project.

## Next Steps

1. **Start here**: [BURSTGPT_QUICKSTART.md](BURSTGPT_QUICKSTART.md)
2. **Learn more**: [BURSTGPT_TRACE_REPLAY.md](BURSTGPT_TRACE_REPLAY.md)
3. **Explore configs**: [burstgpt_configs.md](burstgpt_configs.md)
4. **Run benchmarks**: Use the CLI or bash script

---

**Questions?** Check the documentation files or examine the Python source code - it's well-commented!
