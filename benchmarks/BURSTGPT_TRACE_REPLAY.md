# BurstGPT Trace Replay Benchmark

A comprehensive benchmarking tool for vLLM that replays the BurstGPT dataset traces in online serving mode while maintaining exact input/output token counts and inter-arrival times.

## Features

- **Exact Trace Replay**: Replays requests with the exact inter-arrival times from the BurstGPT trace
- **Token Matching**: Ensures input and output tokens match the dataset specifications
- **Configurable Settings**: Control model, vLLM settings (prefix caching, GPU memory), etc.
- **Comprehensive Metrics**: Collects latency, throughput, time-to-first-token, and token statistics
- **No Failures**: Robust error handling and recovery for production benchmarking
- **Scalable Replay**: Speed up or slow down trace replay with the `--scale` parameter

## Quick Start

### 1. Start vLLM Server

```bash
# Basic setup
vllm serve meta-llama/Llama-2-7b-hf \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.9

# With prefix caching enabled
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.9

# With chunked prefill (for better batching)
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.9

# Multi-GPU setup
vllm serve meta-llama/Llama-2-70b-hf \
    --tensor-parallel-size 4 \
    --enable-prefix-caching \
    --gpu-memory-utilization 0.9
```

### 2. Run the Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/burstgpt_baseline \
    --scale 1.0
```

## Command Line Options

### Required Arguments

- `--trace-path`: Path to the BurstGPT CSV trace file
  - Example: `data/BurstGPT/data/BurstGPT_1.csv`

- `--model`: Model name to use for inference
  - Should match the model loaded on the server
  - Format: can use underscores (e.g., `llama-2-7b-hf`)

### Optional Arguments

- `--base-url` (default: `http://localhost:8000`)
  - vLLM server endpoint
  - Example: `http://192.168.1.100:8000`

- `--output-dir` (default: `results`)
  - Directory to save benchmark results and logs
  - Creates directory if it doesn't exist

- `--scale` (default: `1.0`)
  - Scale factor for inter-arrival times
  - `> 1.0`: Faster replay (e.g., 10.0 = 10x faster)
  - `< 1.0`: Slower replay (e.g., 0.1 = 10x slower)
  - Useful for testing different load levels

- `--num-prompts` (default: None, use all)
  - Limit the number of requests to send
  - Useful for quick tests
  - Example: `--num-prompts 100`

- `--request-rate` (default: None, use trace inter-arrival times)
  - Override trace timing with fixed request rate (requests/sec)
  - Useful for comparison with synthetic workloads
  - Example: `--request-rate 10.0` (10 requests/sec)

- `--enable-streaming` (default: False)
  - Use streaming mode for responses
  - Enables accurate time-to-first-token measurement
  - Recommended for realistic benchmarking

- `--timeout` (default: 300 seconds)
  - Request timeout in seconds
  - Increase for very long responses or slow servers

- `--temperature` (default: 0.0)
  - Sampling temperature for deterministic results
  - 0.0 = greedy (most deterministic)
  - 1.0 = maximum randomness

## Usage Examples

### Example 1: Basic Benchmark

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/baseline
```

### Example 2: With Prefix Caching Enabled

First, start the server with prefix caching:
```bash
vllm serve meta-llama/Llama-2-7b-hf \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --gpu-memory-utilization 0.9
```

Then run the benchmark:
```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/with_prefix_caching \
    --enable-streaming
```

### Example 3: 10x Faster Replay (Load Testing)

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/10x_faster \
    --scale 10.0 \
    --enable-streaming
```

### Example 4: Quick Test with 100 Requests

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/quick_test \
    --num-prompts 100
```

### Example 5: Fixed Request Rate Comparison

```bash
python benchmarks/burstgpt_trace_replay.py \
    --trace-path data/BurstGPT/data/BurstGPT_1.csv \
    --base-url http://localhost:8000 \
    --model llama-2-7b-hf \
    --output-dir results/fixed_rate_5qps \
    --request-rate 5.0 \
    --enable-streaming
```

### Example 6: Multi-Model Comparison Script

```bash
#!/bin/bash

TRACE_PATH="data/BurstGPT/data/BurstGPT_1.csv"
BASE_URL="http://localhost:8000"
SCALE=1.0

# Test multiple models
for MODEL in "llama-2-7b-hf" "mistral-7b" "neural-chat-7b-v3-1"; do
    echo "Testing $MODEL..."

    # Start server with the model
    pkill -f "vllm serve"
    sleep 2

    vllm serve $MODEL \
        --enable-prefix-caching \
        --gpu-memory-utilization 0.9 &

    sleep 10  # Wait for server to start

    # Run benchmark
    python benchmarks/burstgpt_trace_replay.py \
        --trace-path $TRACE_PATH \
        --base-url $BASE_URL \
        --model $MODEL \
        --output-dir results/comparison_$MODEL \
        --scale $SCALE \
        --enable-streaming
done
```

## Output Files

The benchmark generates the following files in `--output-dir`:

### 1. `benchmark.log`
Detailed log file with all benchmark events and statistics
```
2024-03-22 10:30:15,234 - __main__ - INFO - Starting BurstGPT Trace Replay Benchmark
...
2024-03-22 10:35:42,891 - __main__ - INFO - Benchmark Summary
...
```

### 2. `results.json`
Complete benchmark results in JSON format
```json
{
  "benchmark_config": {
    "trace_path": "data/BurstGPT/data/BurstGPT_1.csv",
    "model": "llama-2-7b-hf",
    "scale": 1.0,
    "timestamp": "2024-03-22T10:30:15.234567"
  },
  "summary": {
    "total_requests": 1000,
    "successful_requests": 998,
    "failed_requests": 2
  },
  "metrics": [
    {
      "request_id": 0,
      "timestamp": 1711094415.234567,
      "request_tokens": 472,
      "expected_output_tokens": 18,
      "actual_input_tokens": 472,
      "actual_output_tokens": 18,
      "time_to_first_token": 0.142,
      "total_latency": 0.384,
      "error": null
    },
    ...
  ]
}
```

### 3. `results.csv`
Results in CSV format for spreadsheet analysis
```csv
request_id,timestamp,request_tokens,expected_output_tokens,actual_input_tokens,...
0,1711094415.234,472,18,472,18,0.142,0.384,
1,1711094415.456,1087,230,1087,230,0.156,0.521,
...
```

## Metrics Explained

### Latency Metrics

- **Time to First Token (TTFT)**: Time from request to first response token
  - Measures prefill + first decode latency
  - Critical for interactive applications

- **Total Latency**: Time from request to complete response
  - End-to-end request processing time

### Token Metrics

- **Input Tokens**: Number of prompt tokens sent
- **Output Tokens**: Number of completion tokens generated
- **Tokens/sec**: Throughput in tokens per second

### Throughput

- **Requests/sec**: Number of requests completed per second
- **Total input/output tokens**: Cumulative tokens processed

### Success Rate

- Percentage of successful requests vs failures
- Breakdown of error types

## Troubleshooting

### Issue: Connection Refused
```
Failed to connect to server: ...ConnectionRefusedError...
```

**Solution**: Ensure vLLM server is running
```bash
# Check if server is running
curl http://localhost:8000/v1/models

# Start server if not running
vllm serve meta-llama/Llama-2-7b-hf
```

### Issue: Token Count Mismatch
The benchmark uses the tokenizer from the model to adjust prompt length. If you see significant mismatches:

1. Ensure the tokenizer matches the model
2. The mock tokenizer approximates ~4 chars per token if transformer library isn't available

### Issue: Out of Memory
If you get OOM errors:

1. Reduce GPU memory utilization: `--gpu-memory-utilization 0.7`
2. Enable prefix caching to reduce KV cache: `--enable-prefix-caching`
3. Reduce max concurrent requests in server config

### Issue: Slow Benchmark
If the benchmark is taking too long:

1. Use `--scale 10.0` to replay 10x faster
2. Use `--num-prompts 100` for quick tests
3. Increase request timeout if requests are timing out

## Advanced Customization

### Custom Prompt Generation

Modify the `_generate_prompt_with_tokens()` method to use custom prompts:

```python
def _generate_prompt_with_tokens(self, num_tokens: int) -> str:
    """Generate custom prompt with specific token count."""
    # Your custom prompt generation logic
    base_prompt = "Your custom prompt here: " + " " * num_tokens
    return self._adjust_to_token_count(base_prompt, num_tokens)
```

### Custom Metrics Collection

Extend the `RequestMetrics` dataclass to collect additional metrics:

```python
@dataclass
class CustomMetrics(RequestMetrics):
    cache_hit_rate: float = 0.0
    batch_size: int = 0
    # Add your custom metrics
```

## Performance Tuning Tips

1. **Enable Prefix Caching**: Significantly reduces latency for repeated prefixes
   ```bash
   vllm serve model_name --enable-prefix-caching
   ```

2. **Use Chunked Prefill**: Better batching for high concurrency
   ```bash
   vllm serve model_name --enable-chunked-prefill
   ```

3. **Adjust GPU Memory Utilization**: Balance memory usage and performance
   ```bash
   vllm serve model_name --gpu-memory-utilization 0.9
   ```

4. **Increase Max Batch Tokens**: Higher throughput at cost of latency
   ```bash
   vllm serve model_name --max-num-batched-tokens 8192
   ```

## Dataset Information

The BurstGPT trace contains:
- **Timestamp**: Request arrival time (seconds)
- **Model**: ChatGPT or GPT-4 (informational)
- **Request tokens**: Input prompt token count
- **Response tokens**: Output completion token count
- **Total tokens**: Sum of request + response tokens
- **Log Type**: Conversation log or API log

### Sample Trace Data
```
Timestamp,Model,Request tokens,Response tokens,Total tokens,Log Type
5,ChatGPT,472,18,490,Conversation log
45,ChatGPT,1087,230,1317,Conversation log
118,GPT-4,417,276,693,Conversation log
...
```

## Citation

If you use this benchmark in your research, please cite:

```bibtex
@article{burstgpt,
  title={BurstGPT: Efficient Serving of Large Language Models via Request Bursting},
  year={2024}
}
```

## License

Apache License 2.0
