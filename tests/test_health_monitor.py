import pytest
from unittest.mock import patch, MagicMock
from controller.health_monitor import HealthMonitor
from controller.config import BackendServer
from controller.events import ServerHealthState

@pytest.fixture
def servers():
    return [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3)
    ]

@patch("ryu.lib.hub.spawn")
def test_initial_state(mock_spawn, servers):
    monitor = HealthMonitor(servers)
    assert len(monitor.get_healthy_servers()) == 2
    assert monitor.get_server_state("server1") == ServerHealthState.HEALTHY

@patch("ryu.lib.hub.spawn")
def test_state_change(mock_spawn, servers):
    monitor = HealthMonitor(servers)
    monitor.set_server_state("server1", ServerHealthState.DOWN)
    
    assert len(monitor.get_healthy_servers()) == 1
    assert monitor.get_server_state("server1") == ServerHealthState.DOWN
    assert monitor.get_healthy_servers()[0].id == "server2"
