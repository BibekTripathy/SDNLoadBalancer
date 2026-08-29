import pytest
from unittest.mock import MagicMock
from controller.load_balancer import LoadBalancerEngine
from controller.config import BackendServer

@pytest.fixture
def mock_telemetry():
    return MagicMock()

@pytest.fixture
def mock_health():
    health = MagicMock()
    health.get_healthy_servers.return_value = [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3)
    ]
    return health

def test_load_balancer_connection_tracking(mock_telemetry, mock_health):
    engine = LoadBalancerEngine(telemetry=mock_telemetry, health_monitor=mock_health, default_algorithm="round_robin")
    
    # 1. First connection
    client1 = {"client_ip": "10.0.0.1", "client_port": 1000}
    server_a, reason = engine.select_backend(client1)
    assert server_a.id == "server1"
    
    # 2. Second independent connection
    client2 = {"client_ip": "10.0.0.1", "client_port": 2000}
    server_b, reason = engine.select_backend(client2)
    assert server_b.id == "server2"
    
    # 3. Repeat first connection (ACK or RETRY) -> Should stick to server1!
    server_a_repeat, reason = engine.select_backend(client1)
    assert server_a_repeat.id == "server1"
    assert "Existing connection" in reason
