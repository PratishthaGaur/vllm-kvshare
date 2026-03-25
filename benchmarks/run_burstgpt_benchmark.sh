#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Helper script to run BurstGPT trace replay benchmarks with various configurations

set -e

# Configuration
TRACE_PATH="${TRACE_PATH:-data/BurstGPT/data/BurstGPT_1.csv}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
SCALE="${SCALE:-1.0}"
ENABLE_STREAMING="${ENABLE_STREAMING:-false}"
TIMEOUT="${TIMEOUT:-300}"
RESULTS_DIR="${RESULTS_DIR:-results}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_trace() {
    if [ ! -f "$TRACE_PATH" ]; then
        print_error "Trace file not found: $TRACE_PATH"
        exit 1
    fi
    print_info "Trace file found: $TRACE_PATH"
}

check_server() {
    print_info "Checking server at $BASE_URL..."
    max_retries=5
    retry_count=0

    while [ $retry_count -lt $max_retries ]; do
        if curl -s "${BASE_URL}/v1/models" > /dev/null 2>&1; then
            print_info "Server is ready at $BASE_URL"
            return 0
        fi
        print_warn "Server not ready, retrying... ($((retry_count + 1))/$max_retries)"
        sleep 2
        ((retry_count++))
    done

    print_error "Failed to connect to server at $BASE_URL"
    exit 1
}

run_benchmark() {
    local model=$1
    local config_name=$2
    local extra_args=$3

    local output_dir="${RESULTS_DIR}/burstgpt_${config_name}"

    print_info "Running benchmark: $config_name (model: $model)"
    print_info "Output directory: $output_dir"

    mkdir -p "$output_dir"

    python benchmarks/burstgpt_trace_replay.py \
        --trace-path "$TRACE_PATH" \
        --base-url "$BASE_URL" \
        --model "$model" \
        --output-dir "$output_dir" \
        --scale "$SCALE" \
        --timeout "$TIMEOUT" \
        $extra_args

    print_info "Benchmark completed: $config_name"
    echo ""
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS] COMMAND

Commands:
    baseline        Run baseline benchmark with default settings
    streaming       Run with streaming enabled
    fast            Run 10x faster trace replay
    load-test       Run 100x faster for load testing
    quick           Quick test with only 100 requests
    all             Run all benchmarks in sequence

Options:
    --trace-path PATH       Path to BurstGPT trace (default: $TRACE_PATH)
    --base-url URL          vLLM server URL (default: $BASE_URL)
    --model MODEL           Model name (default: auto-detect from server)
    --scale SCALE           Trace scale factor (default: $SCALE)
    --results-dir DIR       Results directory (default: $RESULTS_DIR)
    --streaming             Enable streaming mode
    --help                  Show this help message

Examples:
    # Run baseline benchmark
    $0 baseline

    # Run with 10x faster replay
    $0 --scale 10.0 fast

    # Run all benchmarks
    $0 all

    # Custom trace and model
    $0 --trace-path custom_trace.csv --model llama-70b baseline
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --trace-path)
            TRACE_PATH="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --scale)
            SCALE="$2"
            shift 2
            ;;
        --results-dir)
            RESULTS_DIR="$2"
            shift 2
            ;;
        --streaming)
            ENABLE_STREAMING=true
            shift
            ;;
        --help)
            usage
            ;;
        baseline|streaming|fast|load-test|quick|all)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

if [ -z "$COMMAND" ]; then
    print_error "No command specified"
    usage
fi

# Pre-flight checks
print_info "Running pre-flight checks..."
check_trace
check_server

# Detect model if not specified
if [ -z "$MODEL" ]; then
    print_info "Detecting model from server..."
    MODEL=$(curl -s "${BASE_URL}/v1/models" | python3 -c "import sys, json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown-model")
    print_info "Detected model: $MODEL"
fi

# Run benchmarks based on command
case $COMMAND in
    baseline)
        run_benchmark "$MODEL" "baseline"
        ;;

    streaming)
        run_benchmark "$MODEL" "streaming" "--enable-streaming"
        ;;

    fast)
        run_benchmark "$MODEL" "10x_faster" "--scale 10.0 --enable-streaming"
        ;;

    load-test)
        run_benchmark "$MODEL" "100x_faster_load" "--scale 100.0 --enable-streaming"
        ;;

    quick)
        run_benchmark "$MODEL" "quick_test" "--num-prompts 100 --enable-streaming"
        ;;

    all)
        print_info "Running all benchmarks..."
        run_benchmark "$MODEL" "1_baseline"
        run_benchmark "$MODEL" "2_streaming" "--enable-streaming"
        run_benchmark "$MODEL" "3_fast" "--scale 10.0 --enable-streaming"
        run_benchmark "$MODEL" "4_quick_test" "--num-prompts 100 --enable-streaming"

        print_info ""
        print_info "All benchmarks completed!"
        print_info "Results saved to: $RESULTS_DIR"
        print_info ""
        print_info "To compare results, check:"
        echo "  - $RESULTS_DIR/burstgpt_*/results.json"
        echo "  - $RESULTS_DIR/burstgpt_*/results.csv"
        echo "  - $RESULTS_DIR/burstgpt_*/benchmark.log"
        ;;
esac

print_info "Done!"
