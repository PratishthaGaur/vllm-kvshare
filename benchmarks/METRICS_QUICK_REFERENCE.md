# Metrics Quick Reference

## Where to Find Each Metric

### 📊 Three Output Files

After running the benchmark, you get:

```
results_dir/
├── benchmark.log          ← Detailed timestamped log
├── results.json          ← Complete data in JSON format
└── results.csv           ← Spreadsheet format
```

---

## 🎯 Per-Request Metrics

**Collected for each of the 1000+ requests**

```
Request #0:
├── request_id: 0                          [Identifies this request]
├── timestamp: 5.23                        [When request was sent (seconds)]
├── request_tokens: 472                    [Input size from trace]
├── expected_output_tokens: 18             [Expected output from trace]
├── actual_input_tokens: 472               [Actual input sent]
├── actual_output_tokens: 18               [Actual output received]
├── time_to_first_token: 0.142            [Prefill latency (seconds)]
├── total_latency: 0.384                   [Full response time (seconds)]
└── error: null                            [null if success, error message if failed]
```

**Find per-request data in:**
- `results.json` → `metrics[]` array
- `results.csv` → each row

---

## 📈 Aggregate Statistics

**Computed from all requests**

### Request Counts
```
Total requests:      1000      [All requests sent]
Successful:           980      [Completed without error]
Failed:                20      [Failed or timed out]
Success rate:       98.0%      [Successful / Total]
```
**Find in:** benchmark.log, results.json summary

### Latency - Total Response Time
```
Mean:        0.486s           [Average time from request to response end]
Median:      0.412s           [50th percentile]
P95:         0.856s           [95% completed within this time]
P99:         1.234s           [99% completed within this time]
```
**Find in:** benchmark.log (printed summary)

### Latency - Time to First Token
```
Mean:       95.23ms           [Average time to first token]
Median:     87.45ms           [50th percentile TTFT]
P95:       234.56ms           [95% received first token within this time]
P99:       456.78ms           [99% received first token within this time]
```
**Find in:** benchmark.log (printed summary)

### Throughput
```
Requests/sec:  4.12            [Successful requests per second]
```
**Find in:** benchmark.log (printed summary)

### Token Statistics
```
Total input tokens:      485,230     [Sum of all input tokens]
Total output tokens:      98,450     [Sum of all output tokens]
Input tokens/sec:       2,047.88     [Tokens per second generated]
Output tokens/sec:        415.49     [Output tokens per second]
```
**Find in:** benchmark.log (printed summary)

### Benchmark Metadata
```
Total benchmark time:   243.52s       [Wall-clock time to run]
Trace path:    ...csv              [Which dataset was used]
Model:         llama-2-7b-hf       [Which model]
Scale:         1.0                 [Replay speed factor]
Timestamp:     2024-03-22T10:30:15 [When benchmark ran]
```
**Find in:** results.json → benchmark_config

---

## 📁 Which File for What?

### I want to... | Use this file
---|---
See all events in order | `benchmark.log`
Export to Excel/Sheets | `results.csv`
Programmatic analysis | `results.json`
Quick human summary | `benchmark.log` (end of file)
Check specific request | `results.csv` (filter by row)
Analyze latency distribution | `results.csv` (import to Python)
Share complete results | `results.json`
Debug failures | `benchmark.log` + `results.csv` (error column)

---

## 🔍 Key Metrics Explained

### Response Latency Distribution
```
Min ─────────── Mean ─────────── Median ────────── P95 ─────── P99 ─ Max
0.05s           0.486s           0.412s            0.856s      1.234s  3.5s

              [Most responses here]
                    |
                    ↓
            ~68% within mean±std
```

- **P99**: Worst 1% of requests
- **P95**: Worst 5% of requests
- **Mean**: Affected by outliers
- **Median**: Better for skewed distributions

### Time to First Token
```
                    [Interactive range]
                           |
       ┌──────────┬────────┴────────┬──────────┐
      0ms        100ms             500ms     1000ms
       ↓          ↓                  ↓         ↓
    Very fast   Good            Noticeable  Slow
```

- <100ms: Feels instant
- 100-500ms: Good for chat
- >500ms: Noticeable delay

---

## 📊 Sample Output

### benchmark.log (tail)
```
2024-03-22 10:35:42,891 - __main__ - INFO - ================================================================================
2024-03-22 10:35:42,892 - __main__ - INFO - Benchmark Summary
2024-03-22 10:35:42,893 - __main__ - INFO - ================================================================================
2024-03-22 10:35:42,894 - __main__ - INFO - Total requests: 980
2024-03-22 10:35:42,895 - __main__ - INFO - Successful: 960
2024-03-22 10:35:42,896 - __main__ - INFO - Failed: 20
2024-03-22 10:35:42,897 - __main__ - INFO - Success rate: 98.00%
2024-03-22 10:35:42,898 - __main__ - INFO -
2024-03-22 10:35:42,899 - __main__ - INFO - Latency Statistics (successful requests only):
2024-03-22 10:35:42,900 - __main__ - INFO -   Total latency:
2024-03-22 10:35:42,901 - __main__ - INFO -     Mean: 0.486s
2024-03-22 10:35:42,902 - __main__ - INFO -     Median: 0.412s
2024-03-22 10:35:42,903 - __main__ - INFO -     P99: 1.234s
2024-03-22 10:35:42,904 - __main__ - INFO -     P95: 0.856s
...
```

### results.csv (first 5 rows)
```
request_id,timestamp,request_tokens,expected_output_tokens,actual_input_tokens,actual_output_tokens,time_to_first_token,total_latency,error
0,5.23,472,18,472,18,0.142,0.384,
1,45.67,1087,230,1087,230,0.156,0.521,
2,118.45,417,276,417,276,0.168,0.495,
3,185.23,1360,647,1360,647,0.184,0.712,
4,214.56,185,215,185,215,0.098,0.345,
```

### results.json (structure)
```json
{
  "benchmark_config": {
    "trace_path": "data/BurstGPT/data/BurstGPT_1.csv",
    "model": "llama-2-7b-hf",
    "base_url": "http://localhost:8000",
    "scale": 1.0,
    "streaming": false,
    "timestamp": "2024-03-22T10:30:15.234567"
  },
  "summary": {
    "total_requests": 980,
    "successful_requests": 960,
    "failed_requests": 20
  },
  "metrics": [
    {"request_id": 0, "timestamp": 5.23, ...},
    {"request_id": 1, "timestamp": 45.67, ...},
    ...
  ]
}
```

---

## 🚀 Quick Analysis Commands

### View Summary
```bash
# Print to console
tail -50 results/benchmark.log

# Just the summary section
grep -A 100 "Benchmark Summary" results/benchmark.log
```

### Python Analysis
```python
import json
with open('results/results.json') as f:
    data = json.load(f)

successful = [m for m in data['metrics'] if m['error'] is None]
print(f"Success: {len(successful)}/{len(data['metrics'])}")
print(f"Mean latency: {sum(m['total_latency'] for m in successful) / len(successful):.3f}s")
```

### Spreadsheet Import
```bash
# Copy to clipboard
cat results/results.csv | pbcopy

# Or open directly
open results/results.csv
```

### Comparison
```bash
python analyze_burstgpt_results.py \
    --compare results/config_a results/config_b \
    --output-format table
```

---

## 📌 Critical Metrics to Monitor

| Metric | Target | If Worse | Action |
|--------|--------|----------|--------|
| **Success rate** | >95% | Lower | Check server logs |
| **P99 latency** | <2s | Higher | Optimize KV cache or batch size |
| **TTFT P99** | <500ms | Higher | Enable prefix caching |
| **Output tokens/sec** | >100 | Lower | Check GPU utilization |

---

## 🔗 Related Guides

- **Full documentation**: [METRICS_GUIDE.md](METRICS_GUIDE.md)
- **Usage examples**: [BURSTGPT_TRACE_REPLAY.md](BURSTGPT_TRACE_REPLAY.md)
- **Duration control**: [DURATION_LIMIT_EXAMPLES.md](DURATION_LIMIT_EXAMPLES.md)
- **Configuration examples**: [burstgpt_configs.md](burstgpt_configs.md)

