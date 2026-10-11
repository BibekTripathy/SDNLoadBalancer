"""
Unit tests for dynamic backend server registry, validation, and lifecycle management.
"""

import pytest
from controller.config import BackendServer, NetworkConfig
from controller.health_monitor import HealthMonitor
from controller.telemetry import TelemetryCollector
from controller.load_balancer import LoadBalancerEngine
from controller.events import ServerHealthState


@pytest.fixture
def clean_config():
    """Provides a fresh NetworkConfig instance with standard default servers."""
    return NetworkConfig()


def test_add_server_success(clean_config):
    new_srv = BackendServer(id="server4", ip="10.0.0.5", port=80, switch_port=5, weight=2)
    clean_config.add_server(new_srv)

    assert len(clean_config.SERVERS) == 4
    assert clean_config.get_server("server4") == new_srv
    assert clean_config.get_server("server4").mac == "00:00:00:00:00:05"


def test_add_server_duplicate_id_rejected(clean_config):
    dup_srv = BackendServer(id="server1", ip="10.0.0.9", port=80, switch_port=9)
    with pytest.raises(ValueError, match="already registered"):
        clean_config.add_server(dup_srv)


def test_add_server_duplicate_ip_rejected(clean_config):
    dup_ip_srv = BackendServer(id="server99", ip="10.0.0.2", port=80, switch_port=9)
    with pytest.raises(ValueError, match="already assigned to an existing backend"):
        clean_config.add_server(dup_ip_srv)


def test_add_server_reserved_ips_rejected(clean_config):
    client_ip_srv = BackendServer(id="server99", ip="10.0.0.1", port=80, switch_port=9)
    with pytest.raises(ValueError, match="conflicts with reserved"):
        clean_config.add_server(client_ip_srv)

    vip_srv = BackendServer(id="server99", ip="10.0.0.100", port=80, switch_port=9)
    with pytest.raises(ValueError, match="conflicts with reserved"):
        clean_config.add_server(vip_srv)


def test_add_server_reserved_switch_port_rejected(clean_config):
    client_port_srv = BackendServer(id="server99", ip="10.0.0.9", port=80, switch_port=1)
    with pytest.raises(ValueError, match="reserved for the Client host"):
        clean_config.add_server(client_port_srv)


def test_add_server_duplicate_switch_port_rejected(clean_config):
    dup_port_srv = BackendServer(id="server99", ip="10.0.0.9", port=80, switch_port=2)
    with pytest.raises(ValueError, match="already assigned to another backend"):
        clean_config.add_server(dup_port_srv)


def test_add_server_invalid_weight(clean_config):
    bad_weight_srv = BackendServer(id="server99", ip="10.0.0.9", port=80, switch_port=9, weight=0)
    with pytest.raises(ValueError, match="weight must be at least 1"):
        clean_config.add_server(bad_weight_srv)


def test_remove_server_success(clean_config):
    initial_count = len(clean_config.SERVERS)
    removed = clean_config.remove_server("server2")
    assert removed.id == "server2"
    assert len(clean_config.SERVERS) == initial_count - 1
    assert clean_config.get_server("server2") is None


def test_remove_server_not_found(clean_config):
    with pytest.raises(KeyError, match="not found"):
        clean_config.remove_server("nonexistent_server")


def test_update_server_weight(clean_config):
    clean_config.update_server_weight("server1", 10)
    assert clean_config.get_server("server1").weight == 10

    with pytest.raises(ValueError, match="at least 1"):
        clean_config.update_server_weight("server1", 0)


def test_suggest_next_server_config(clean_config):
    suggestion = clean_config.suggest_next_server_config()
    assert suggestion["id"] == "server4"
    assert suggestion["ip"] == "10.0.0.5"
    assert suggestion["switch_port"] == 5
    assert suggestion["port"] == 80
    assert suggestion["weight"] == 1


def test_health_monitor_dynamic_lifecycle(clean_config):
    monitor = HealthMonitor(clean_config.SERVERS)
    assert len(monitor.get_healthy_servers()) == 3

    # Add server
    new_srv = BackendServer(id="server4", ip="10.0.0.5", port=80, switch_port=5)
    monitor.add_server(new_srv, initial_state=ServerHealthState.HEALTHY)
    assert len(monitor.get_healthy_servers()) == 4
    assert monitor.get_server_state("server4") == ServerHealthState.HEALTHY

    # Mark draining
    monitor.set_server_state("server4", ServerHealthState.DRAINING, reason="test drain")
    assert monitor.get_server_state("server4") == ServerHealthState.DRAINING
    # Draining servers must NOT be in healthy list
    assert "server4" not in [s.id for s in monitor.get_healthy_servers()]

    # Remove server
    monitor.remove_server("server4")
    assert "server4" not in monitor.servers
    assert monitor.get_server_state("server4") == ServerHealthState.DOWN


def test_telemetry_dynamic_lifecycle(clean_config):
    telemetry = TelemetryCollector(clean_config.SERVERS)
    assert len(telemetry.get_all_metrics()) == 3

    # Add server
    new_srv = BackendServer(id="server4", ip="10.0.0.5", port=80, switch_port=5)
    telemetry.add_server(new_srv)
    assert "server4" in telemetry.get_all_metrics()
    assert telemetry.metrics["server4"].switch_port == 5

    # Remove server
    telemetry.remove_server("server4")
    assert "server4" not in telemetry.get_all_metrics()
    assert 5 not in telemetry.servers_by_port


def test_load_balancer_cleanup_on_server_remove(clean_config):
    monitor = HealthMonitor(clean_config.SERVERS)
    telemetry = TelemetryCollector(clean_config.SERVERS)
    engine = LoadBalancerEngine(telemetry, monitor)

    # Establish an active connection to server1
    client_info = {"client_ip": "10.0.0.1", "client_port": 12345}
    srv, _ = engine.select_backend(client_info)
    assert ("10.0.0.1", 12345) in engine.active_connections

    # Cleanup connections for that server
    cleaned = engine.cleanup_server_connections(srv.id)
    assert cleaned >= 1
    assert ("10.0.0.1", 12345) not in engine.active_connections
