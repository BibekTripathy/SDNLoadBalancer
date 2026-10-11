"""
Export utilities for the Benchmarking Laboratory.
Generates structured CSV and JSON downloads containing full experiment configurations,
per-repetition measurements, units, timestamps, and time-series samples.
"""

import csv
import io
import json
from typing import Any, Dict
from api.benchmark.models import BenchmarkDetails


def generate_benchmark_csv(benchmark: BenchmarkDetails) -> str:
    """
    Generates CSV text representation of all benchmark runs and aggregate results.
    Includes metric units, timestamps, and documented sources.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Header Metadata Section
    writer.writerow(["# Experiment Name", benchmark.name])
    writer.writerow(["# Experiment ID", benchmark.id])
    writer.writerow(["# Created At (UTC)", benchmark.created_at])
    writer.writerow(["# Mode", "Simulated" if benchmark.is_simulated else "Live Mininet OpenFlow Network"])
    writer.writerow(["# Status", benchmark.status.value])
    writer.writerow(["# Target Endpoint", benchmark.config.target_url])
    writer.writerow(["# Configured Rate (RPS)", benchmark.config.rate])
    writer.writerow(["# Concurrency Workers", benchmark.config.concurrency])
    writer.writerow(["# Duration Per Run (s)", benchmark.config.duration])
    writer.writerow(["# Warm-up Excluded (s)", benchmark.config.warmup_duration])
    writer.writerow([])

    # 2. Per-Repetition Run Results Table
    writer.writerow([
        "Algorithm",
        "Repetition",
        "Total Requests",
        "Successful Requests",
        "Failed Requests",
        "Error Rate (%)",
        "Achieved RPS (req/s)",
        "Throughput (Mbps)",
        "Mean Latency (ms)",
        "p50 Latency (ms)",
        "p95 Latency (ms)",
        "p99 Latency (ms)",
        "Jain's Fairness Index (0-1)",
        "Recovery Time (s)",
        "Server1 Requests",
        "Server2 Requests",
        "Server3 Requests",
        "Is Simulated",
    ])

    for run in benchmark.runs:
        writer.writerow([
            run.algorithm,
            run.repetition,
            run.total_requests,
            run.successful_requests,
            run.failed_requests,
            run.error_rate_pct,
            run.achieved_rps,
            run.throughput_mbps,
            run.mean_latency_ms,
            run.p50_latency_ms,
            run.p95_latency_ms,
            run.p99_latency_ms,
            run.jains_fairness_index,
            run.recovery_time_sec if run.recovery_time_sec is not None else "N/A",
            run.backend_distribution.get("server1", 0),
            run.backend_distribution.get("server2", 0),
            run.backend_distribution.get("server3", 0),
            "True" if run.is_simulated else "False",
        ])

    writer.writerow([])
    # 3. Aggregate Summaries Table
    writer.writerow([
        "# AGGREGATE ALGORITHM SUMMARIES",
        "Repetitions",
        "Mean RPS (req/s)",
        "Mean Latency (ms)",
        "p95 Latency (ms)",
        "Mean Error Rate (%)",
        "Mean Throughput (Mbps)",
        "Jain's Fairness Index",
        "Avg Recovery Time (s)",
    ])

    for s in benchmark.summary:
        writer.writerow([
            s.algorithm,
            s.repetition_count,
            s.mean_achieved_rps,
            s.mean_latency_ms,
            s.p95_latency_ms,
            s.mean_error_rate_pct,
            s.mean_throughput_mbps,
            s.jains_fairness_index,
            s.recovery_time_sec if s.recovery_time_sec is not None else "N/A",
        ])

    return output.getvalue()


def generate_benchmark_json(benchmark: BenchmarkDetails) -> Dict[str, Any]:
    """Returns dictionary dump of benchmark with metric units and metadata."""
    data = benchmark.model_dump()
    data["metadata"] = {
        "export_timestamp": benchmark.created_at,
        "metric_units": {
            "rate": "requests per second (req/s)",
            "throughput": "Megabits per second (Mbps)",
            "latency": "milliseconds (ms)",
            "duration": "seconds (s)",
            "fairness": "Jain's index (0.0 to 1.0, where 1.0 is perfectly balanced)",
        },
        "metric_sources": {
            "throughput_mbps": "Calculated: (total steady-state response payload bytes * 8) / (duration * 10^6)",
            "latency_percentiles": "High-resolution monotonic timer measurements with linear interpolation",
            "jains_fairness": "Equation: (sum(x_i))^2 / (n * sum(x_i^2)) evaluated on serving backend counts",
            "backend_distribution": "Extracted directly from backend JSON response server_id field",
        },
    }
    return data
