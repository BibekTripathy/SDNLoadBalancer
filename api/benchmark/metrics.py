"""
Statistical and mathematical metric calculation utilities for the Benchmarking Laboratory.
Includes Jain's Fairness Index, latency percentiles, throughput, and cross-repetition aggregation.
"""

from typing import Dict, List, Optional
from api.benchmark.models import AlgorithmSummary, RunMetrics


def calculate_percentile(data: List[float], percentile: float) -> float:
    """
    Computes precise percentile using linear interpolation (same as NumPy default).

    Args:
        data: List of numeric values (latencies in ms).
        percentile: Float between 0.0 and 100.0 (e.g. 50.0, 95.0, 99.0).

    Returns:
        Interpolated percentile rounded to 2 decimal places, or 0.0 if data is empty.
    """
    if not data:
        return 0.0
    if len(data) == 1:
        return round(float(data[0]), 2)

    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    floor_idx = int(k)
    ceil_idx = min(floor_idx + 1, len(sorted_data) - 1)
    weight = k - floor_idx
    interpolated = sorted_data[floor_idx] * (1.0 - weight) + sorted_data[ceil_idx] * weight
    return round(float(interpolated), 2)


def calculate_jains_fairness_index(distribution: Dict[str, int], eligible_server_count: int) -> float:
    r"""
    Calculates Jain's Fairness Index:
        J = ( \sum_{i=1}^n x_i )^2 / ( n * \sum_{i=1}^n x_i^2 )

    Measures the degree of equality of request distribution across n eligible backends.
    Value ranges from 1/n (worst case: all requests sent to a single server)
    to 1.0 (perfectly balanced: all servers handle exactly identical request counts).

    Note: Fairness measures equal balance, which is optimal for homogeneous server pools.
    For weighted distributions (e.g. Weighted Round Robin), J reflects balance rather than weight fidelity.
    """
    if eligible_server_count <= 0:
        return 1.0

    counts = [float(v) for v in distribution.values()]
    # Account for any eligible servers that received 0 requests
    missing_servers = eligible_server_count - len(counts)
    if missing_servers > 0:
        counts.extend([0.0] * missing_servers)

    sum_x = sum(counts)
    if sum_x == 0.0:
        return 1.0

    sum_x_sq = sum(x * x for x in counts)
    if sum_x_sq == 0.0:
        return 1.0

    jain_index = (sum_x ** 2) / (float(eligible_server_count) * sum_x_sq)
    return round(max(0.0, min(1.0, jain_index)), 4)


def calculate_throughput_mbps(total_bytes: int, duration_seconds: float) -> float:
    """
    Computes network throughput in Megabits per second (Mbps).

    Source: Total response body and headers transfer bytes over steady-state test duration.
    Unit: Megabits per second (1 Mbps = 1,000,000 bits/sec).
    """
    if duration_seconds <= 0 or total_bytes <= 0:
        return 0.0
    bits = total_bytes * 8.0
    mbps = bits / (duration_seconds * 1_000_000.0)
    return round(mbps, 3)


def calculate_error_rate_pct(failed_count: int, total_count: int) -> float:
    """Computes error percentage (0.0% to 100.0%)."""
    if total_count <= 0:
        return 0.0
    return round((failed_count / total_count) * 100.0, 2)


def aggregate_runs(runs: List[RunMetrics], eligible_server_count: int) -> AlgorithmSummary:
    """
    Aggregates steady-state performance across multiple repetitions for an algorithm.
    Computes mean throughput, latency, error rate, and consolidated distribution.
    """
    if not runs:
        raise ValueError("Cannot aggregate empty run metrics list")

    algo = runs[0].algorithm
    count = len(runs)
    is_sim = any(r.is_simulated for r in runs)

    mean_rps = sum(r.achieved_rps for r in runs) / count
    mean_lat = sum(r.mean_latency_ms for r in runs) / count
    mean_p95 = sum(r.p95_latency_ms for r in runs) / count
    mean_err = sum(r.error_rate_pct for r in runs) / count
    mean_mbps = sum(r.throughput_mbps for r in runs) / count

    # Combine distributions across all repetitions
    aggregate_dist: Dict[str, int] = {}
    for r in runs:
        for sid, cnt in r.backend_distribution.items():
            aggregate_dist[sid] = aggregate_dist.get(sid, 0) + cnt

    jain = calculate_jains_fairness_index(aggregate_dist, eligible_server_count)

    recovery_times = [r.recovery_time_sec for r in runs if r.recovery_time_sec is not None]
    avg_recovery = (sum(recovery_times) / len(recovery_times)) if recovery_times else None

    return AlgorithmSummary(
        algorithm=algo,
        repetition_count=count,
        mean_achieved_rps=round(mean_rps, 2),
        mean_latency_ms=round(mean_lat, 2),
        p95_latency_ms=round(mean_p95, 2),
        mean_error_rate_pct=round(mean_err, 2),
        mean_throughput_mbps=round(mean_mbps, 3),
        aggregate_distribution=aggregate_dist,
        jains_fairness_index=jain,
        recovery_time_sec=round(avg_recovery, 2) if avg_recovery is not None else None,
        is_simulated=is_sim,
    )
