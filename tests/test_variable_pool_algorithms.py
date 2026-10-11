"""
Tests for all 6 load balancing algorithms with variable server pool sizes (1, 3, 5, empty, dynamic).
"""

import pytest
from controller.algorithms import (
    AdaptiveAlgorithm,
    LeastBandwidthAlgorithm,
    LeastConnectionsAlgorithm,
    RandomAlgorithm,
    RoundRobinAlgorithm,
    WeightedRoundRobinAlgorithm,
)
from controller.config import BackendServer


@pytest.fixture
def single_server():
    return [
        BackendServer(id="server1", ip="10.0.0.2", port=80, switch_port=2, weight=1),
    ]


@pytest.fixture
def five_servers():
    return [
        BackendServer(id="server1", ip="10.0.0.2", port=80, switch_port=2, weight=1),
        BackendServer(id="server2", ip="10.0.0.3", port=80, switch_port=3, weight=2),
        BackendServer(id="server3", ip="10.0.0.4", port=80, switch_port=4, weight=3),
        BackendServer(id="server4", ip="10.0.0.5", port=80, switch_port=5, weight=4),
        BackendServer(id="server5", ip="10.0.0.6", port=80, switch_port=6, weight=5),
    ]


@pytest.fixture
def client_info():
    return {
        "client_ip": "10.0.0.1",
        "client_port": 50000,
        "dest_ip": "10.0.0.100",
        "dest_port": 80,
        "protocol": "TCP",
    }


def test_empty_pool_all_algorithms(client_info):
    """Every algorithm must safely reject empty server pools with ValueError."""
    algos = [
        RoundRobinAlgorithm(),
        WeightedRoundRobinAlgorithm(),
        LeastConnectionsAlgorithm(),
        LeastBandwidthAlgorithm(),
        RandomAlgorithm(),
        AdaptiveAlgorithm(),
    ]

    for algo in algos:
        with pytest.raises(ValueError, match="No healthy backend servers"):
            algo.select_server([], client_info, {})


def test_single_server_pool_all_algorithms(single_server, client_info):
    """Every algorithm must function correctly when exactly one backend server is present."""
    telemetry = {
        "server1": {
            "bandwidth_mbps": 1.5,
            "active_connections": 3,
            "latency_ms": 2.0,
            "packet_loss_ratio": 0.0,
        }
    }

    algos = [
        RoundRobinAlgorithm(),
        WeightedRoundRobinAlgorithm(),
        LeastConnectionsAlgorithm(),
        LeastBandwidthAlgorithm(),
        RandomAlgorithm(),
        AdaptiveAlgorithm(),
    ]

    for algo in algos:
        selected, reasoning = algo.select_server(single_server, client_info, telemetry)
        assert selected.id == "server1"
        assert selected.ip == "10.0.0.2"


def test_five_servers_round_robin(five_servers, client_info):
    rr = RoundRobinAlgorithm()
    selections = [rr.select_server(five_servers, client_info, {})[0].id for _ in range(10)]
    expected = [
        "server1", "server2", "server3", "server4", "server5",
        "server1", "server2", "server3", "server4", "server5",
    ]
    assert selections == expected


def test_five_servers_weighted_round_robin(five_servers, client_info):
    wrr = WeightedRoundRobinAlgorithm()
    # Weights are 1, 2, 3, 4, 5 => total = 15
    counts = {s.id: 0 for s in five_servers}
    for _ in range(15):
        selected, _ = wrr.select_server(five_servers, client_info, {})
        counts[selected.id] += 1

    assert counts["server1"] == 1
    assert counts["server2"] == 2
    assert counts["server3"] == 3
    assert counts["server4"] == 4
    assert counts["server5"] == 5


def test_five_servers_least_connections(five_servers, client_info):
    lc = LeastConnectionsAlgorithm()
    telemetry = {
        "server1": {"active_connections": 10},
        "server2": {"active_connections": 15},
        "server3": {"active_connections": 2},  # lowest
        "server4": {"active_connections": 8},
        "server5": {"active_connections": 6},
    }
    selected, reason = lc.select_server(five_servers, client_info, telemetry)
    assert selected.id == "server3"
    assert reason["min_connections"] == 2


def test_five_servers_least_bandwidth(five_servers, client_info):
    lb = LeastBandwidthAlgorithm()
    telemetry = {
        "server1": {"bandwidth_mbps": 4.5},
        "server2": {"bandwidth_mbps": 1.2},
        "server3": {"bandwidth_mbps": 3.0},
        "server4": {"bandwidth_mbps": 0.4},  # lowest
        "server5": {"bandwidth_mbps": 2.1},
    }
    selected, reason = lb.select_server(five_servers, client_info, telemetry)
    assert selected.id == "server4"
    assert reason["min_bandwidth_mbps"] == 0.4


def test_five_servers_adaptive(five_servers, client_info):
    adaptive = AdaptiveAlgorithm()
    telemetry = {
        "server1": {"bandwidth_mbps": 10.0, "active_connections": 20, "latency_ms": 10.0, "packet_loss_ratio": 0.05},
        "server2": {"bandwidth_mbps": 8.0, "active_connections": 15, "latency_ms": 8.0, "packet_loss_ratio": 0.02},
        "server3": {"bandwidth_mbps": 5.0, "active_connections": 10, "latency_ms": 5.0, "packet_loss_ratio": 0.01},
        "server4": {"bandwidth_mbps": 2.0, "active_connections": 5, "latency_ms": 2.0, "packet_loss_ratio": 0.0},
        "server5": {"bandwidth_mbps": 0.5, "active_connections": 1, "latency_ms": 1.0, "packet_loss_ratio": 0.0}, # lowest all
    }
    selected, reason = adaptive.select_server(five_servers, client_info, telemetry)
    assert selected.id == "server5"
    assert reason["selected_server"] == "server5"


def test_dynamic_shrink_pool_wrr(five_servers, client_info):
    """Verifies Weighted Round Robin transitions gracefully when server pool shrinks dynamically."""
    wrr = WeightedRoundRobinAlgorithm()
    # Cycle twice on 5 servers
    for _ in range(5):
        wrr.select_server(five_servers, client_info, {})

    # Shrink pool to 2 servers
    shrunk_pool = five_servers[:2]
    # Should not throw IndexError or deadlock
    for _ in range(6):
        selected, _ = wrr.select_server(shrunk_pool, client_info, {})
        assert selected.id in ["server1", "server2"]
