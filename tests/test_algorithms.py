"""
Unit tests for SDN Load Balancing Algorithms.
"""

import pytest
from controller.algorithms import (
    AdaptiveAlgorithm,
    LeastBandwidthAlgorithm,
    LeastConnectionsAlgorithm,
    RandomAlgorithm,
    RoundRobinAlgorithm,
    WeightedRoundRobinAlgorithm,
    get_algorithm,
    list_available_algorithms,
)
from controller.config import BackendServer


@pytest.fixture
def sample_servers():
    return [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2, weight=1),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3, weight=2),
        BackendServer(id="server3", ip="10.0.0.4", mac="00:00:00:00:00:04", port=80, switch_port=4, weight=3),
    ]


@pytest.fixture
def sample_client_info():
    return {
        "client_ip": "10.0.0.1",
        "client_port": 54321,
        "dest_ip": "10.0.0.100",
        "dest_port": 80,
        "protocol": "TCP",
    }


def test_round_robin_distribution(sample_servers, sample_client_info):
    rr = RoundRobinAlgorithm()
    selections = []
    for _ in range(6):
        selected, _ = rr.select_server(sample_servers, sample_client_info, {})
        selections.append(selected.id)

    assert selections == ["server1", "server2", "server3", "server1", "server2", "server3"]


def test_random_algorithm(sample_servers, sample_client_info):
    rand_algo = RandomAlgorithm()
    selected, reason = rand_algo.select_server(sample_servers, sample_client_info, {})
    assert selected in sample_servers
    assert reason["algorithm"] == "random"


def test_least_connections_algorithm(sample_servers, sample_client_info):
    lc = LeastConnectionsAlgorithm()
    telemetry = {
        "server1": {"active_connections": 10},
        "server2": {"active_connections": 2},  # lowest
        "server3": {"active_connections": 7},
    }
    selected, reason = lc.select_server(sample_servers, sample_client_info, telemetry)
    assert selected.id == "server2"
    assert reason["min_connections"] == 2


def test_least_bandwidth_algorithm(sample_servers, sample_client_info):
    lb = LeastBandwidthAlgorithm()
    telemetry = {
        "server1": {"bandwidth_mbps": 18.5},
        "server2": {"bandwidth_mbps": 25.1},
        "server3": {"bandwidth_mbps": 4.2},  # lowest
    }
    selected, reason = lb.select_server(sample_servers, sample_client_info, telemetry)
    assert selected.id == "server3"
    assert reason["min_bandwidth_mbps"] == 4.2


def test_weighted_round_robin(sample_servers, sample_client_info):
    wrr = WeightedRoundRobinAlgorithm()
    # Weights: server1=1, server2=2, server3=3 -> Total sum = 6
    counts = {"server1": 0, "server2": 0, "server3": 0}
    for _ in range(60):
        selected, _ = wrr.select_server(sample_servers, sample_client_info, {})
        counts[selected.id] += 1

    # Ratio should match weights: 10 : 20 : 30
    assert counts["server1"] == 10
    assert counts["server2"] == 20
    assert counts["server3"] == 30


def test_adaptive_algorithm_scoring(sample_servers, sample_client_info):
    adaptive = AdaptiveAlgorithm(
        weight_bandwidth=0.4,
        weight_connections=0.3,
        weight_latency=0.2,
        weight_loss=0.1,
    )
    telemetry = {
        "server1": {"bandwidth_mbps": 80.0, "active_connections": 50, "latency_ms": 20.0, "packet_loss_ratio": 0.05},
        "server2": {"bandwidth_mbps": 50.0, "active_connections": 30, "latency_ms": 10.0, "packet_loss_ratio": 0.01},
        "server3": {"bandwidth_mbps": 10.0, "active_connections": 5, "latency_ms": 2.0, "packet_loss_ratio": 0.0},  # best
    }
    selected, reason = adaptive.select_server(sample_servers, sample_client_info, telemetry)
    assert selected.id == "server3"
    assert "breakdowns" in reason
    assert reason["breakdowns"]["server3"]["composite_score"] == 0.0


def test_algorithm_registry():
    available = list_available_algorithms()
    assert len(available) == 6
    algo = get_algorithm("adaptive")
    assert isinstance(algo, AdaptiveAlgorithm)

    with pytest.raises(ValueError):
        get_algorithm("non_existent_algorithm")
