"""
Unit tests for Benchmarking Laboratory metric calculations.
Tests Jain's Fairness Index, percentiles, error rates, throughput, and cross-run aggregation.
"""

import pytest
from api.benchmark.metrics import (
    calculate_error_rate_pct,
    calculate_jains_fairness_index,
    calculate_percentile,
    calculate_throughput_mbps,
    aggregate_runs,
)
from api.benchmark.models import RunMetrics


def test_percentile_calculation():
    # Empty
    assert calculate_percentile([], 95.0) == 0.0

    # Single item
    assert calculate_percentile([10.5], 95.0) == 10.5

    # Uniform sequence 1 to 100
    data = list(range(1, 101))
    p50 = calculate_percentile(data, 50.0)
    p95 = calculate_percentile(data, 95.0)
    p99 = calculate_percentile(data, 99.0)

    assert p50 == pytest.approx(50.5, rel=1e-2)
    assert p95 == pytest.approx(95.05, rel=1e-2)
    assert p99 == pytest.approx(99.01, rel=1e-2)


def test_jains_fairness_index():
    # Perfectly balanced across 3 servers (100, 100, 100) -> J = 1.0
    dist_equal = {"server1": 100, "server2": 100, "server3": 100}
    assert calculate_jains_fairness_index(dist_equal, 3) == 1.0

    # Completely skewed to 1 server out of 3 -> J = (300)^2 / (3 * 300^2) = 1/3 = 0.3333
    dist_skewed = {"server1": 300, "server2": 0, "server3": 0}
    assert calculate_jains_fairness_index(dist_skewed, 3) == pytest.approx(0.3333, abs=1e-3)

    # Missing eligible servers accounted for (e.g. only 2 servers in map, but 3 eligible)
    dist_partial = {"server1": 150, "server2": 150}
    # (300)^2 / (3 * (150^2 + 150^2 + 0^2)) = 90000 / (3 * 45000) = 90000 / 135000 = 0.6667
    assert calculate_jains_fairness_index(dist_partial, 3) == pytest.approx(0.6667, abs=1e-3)

    # Empty
    assert calculate_jains_fairness_index({}, 3) == 1.0


def test_throughput_mbps():
    assert calculate_throughput_mbps(0, 10.0) == 0.0
    assert calculate_throughput_mbps(125_000, 1.0) == 1.0  # 125,000 bytes * 8 = 1,000,000 bits = 1.0 Mbps
    assert calculate_throughput_mbps(250_000, 2.0) == 1.0


def test_error_rate_pct():
    assert calculate_error_rate_pct(0, 100) == 0.0
    assert calculate_error_rate_pct(5, 100) == 5.0
    assert calculate_error_rate_pct(100, 100) == 100.0
    assert calculate_error_rate_pct(0, 0) == 0.0


def test_aggregate_runs():
    run1 = RunMetrics(
        algorithm="round_robin",
        repetition=1,
        total_requests=100,
        successful_requests=100,
        failed_requests=0,
        error_rate_pct=0.0,
        achieved_rps=20.0,
        throughput_mbps=0.4,
        mean_latency_ms=2.0,
        p50_latency_ms=1.9,
        p95_latency_ms=2.5,
        p99_latency_ms=3.0,
        backend_distribution={"server1": 34, "server2": 33, "server3": 33},
        jains_fairness_index=1.0,
        is_simulated=True,
    )

    run2 = RunMetrics(
        algorithm="round_robin",
        repetition=2,
        total_requests=100,
        successful_requests=98,
        failed_requests=2,
        error_rate_pct=2.0,
        achieved_rps=19.6,
        throughput_mbps=0.38,
        mean_latency_ms=2.2,
        p50_latency_ms=2.0,
        p95_latency_ms=2.7,
        p99_latency_ms=3.2,
        backend_distribution={"server1": 33, "server2": 33, "server3": 32},
        jains_fairness_index=1.0,
        is_simulated=True,
    )

    summary = aggregate_runs([run1, run2], eligible_server_count=3)
    assert summary.algorithm == "round_robin"
    assert summary.repetition_count == 2
    assert summary.mean_achieved_rps == pytest.approx(19.8, rel=1e-2)
    assert summary.mean_latency_ms == pytest.approx(2.1, rel=1e-2)
    assert summary.mean_error_rate_pct == pytest.approx(1.0, rel=1e-2)
    assert summary.aggregate_distribution == {"server1": 67, "server2": 66, "server3": 65}
    assert summary.is_simulated is True
