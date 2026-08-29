"""
Configuration settings for SDN Dynamic Load Balancer.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BackendServer:
    """Backend server configuration model."""
    id: str
    ip: str
    mac: str
    port: int
    switch_port: int
    weight: int = 1


@dataclass
class NetworkConfig:
    """Network and Controller configuration constants."""
    # Virtual IP exposed to client
    VIRTUAL_IP: str = "10.0.0.100"
    VIRTUAL_MAC: str = "00:00:00:00:00:FE"
    
    # Client host config
    CLIENT_IP: str = "10.0.0.1"
    CLIENT_MAC: str = "00:00:00:00:00:01"
    CLIENT_SWITCH_PORT: int = 1
    
    # Backend server pool
    SERVERS: List[BackendServer] = field(default_factory=lambda: [
        BackendServer(id="server1", ip="10.0.0.2", mac="00:00:00:00:00:02", port=80, switch_port=2, weight=1),
        BackendServer(id="server2", ip="10.0.0.3", mac="00:00:00:00:00:03", port=80, switch_port=3, weight=2),
        BackendServer(id="server3", ip="10.0.0.4", mac="00:00:00:00:00:04", port=80, switch_port=4, weight=3),
    ])
    
    # OpenFlow Flow Timeouts
    IDLE_TIMEOUT: int = 15
    HARD_TIMEOUT: int = 30
    
    # Telemetry polling interval (seconds)
    STAT_INTERVAL: float = 2.0
    
    # Health check interval (seconds)
    HEALTH_CHECK_INTERVAL: float = 3.0
    
    # OpenFlow Priorities
    PRIORITY_HIGH: int = 100
    PRIORITY_MEDIUM: int = 50
    PRIORITY_LOW: int = 10
    PRIORITY_TABLE_MISS: int = 0


CONFIG = NetworkConfig()
