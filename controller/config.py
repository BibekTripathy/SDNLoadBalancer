import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BackendServer:
    """Backend server configuration model."""
    id: str
    ip: str
    mac: str = ""
    port: int = 80
    switch_port: int = 1
    weight: int = 1
    status: str = "HEALTHY"
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.mac and self.switch_port:
            self.mac = f"00:00:00:00:00:{self.switch_port:02x}"


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

    def get_server(self, server_id: str) -> Optional[BackendServer]:
        """Finds a backend server by ID."""
        for s in self.SERVERS:
            if s.id == server_id:
                return s
        return None

    def add_server(self, server: BackendServer) -> BackendServer:
        """
        Validates and adds a new backend server to the configuration registry.
        Enforces unique server ID, IP address, and switch port constraints.
        """
        if not server.id or not server.id.strip():
            raise ValueError("Server ID cannot be empty")
        server_id = server.id.strip()

        if self.get_server(server_id) is not None:
            raise ValueError(f"Server ID '{server_id}' is already registered")

        if server.ip in [s.ip for s in self.SERVERS]:
            raise ValueError(f"IP address '{server.ip}' is already assigned to an existing backend")
        if server.ip in [self.CLIENT_IP, self.VIRTUAL_IP]:
            raise ValueError(f"IP address '{server.ip}' conflicts with reserved client or virtual IP")

        if server.switch_port == self.CLIENT_SWITCH_PORT:
            raise ValueError(f"Switch port {server.switch_port} is reserved for the Client host")
        if server.switch_port in [s.switch_port for s in self.SERVERS]:
            raise ValueError(f"Switch port {server.switch_port} is already assigned to another backend")

        if server.weight < 1:
            raise ValueError("Server weight must be at least 1")

        if not server.mac:
            server.mac = f"00:00:00:00:00:{server.switch_port:02x}"

        self.SERVERS.append(server)
        return server

    def remove_server(self, server_id: str) -> BackendServer:
        """Removes a backend server from the configuration registry."""
        server = self.get_server(server_id)
        if server is None:
            raise KeyError(f"Server ID '{server_id}' not found in registry")
        self.SERVERS.remove(server)
        return server

    def update_server_weight(self, server_id: str, weight: int) -> BackendServer:
        """Updates the configured capacity weight for a server."""
        if weight < 1:
            raise ValueError("Weight must be at least 1")
        server = self.get_server(server_id)
        if server is None:
            raise KeyError(f"Server ID '{server_id}' not found in registry")
        server.weight = weight
        return server

    def suggest_next_server_config(self) -> Dict[str, Any]:
        """
        Calculates the next available default server ID, IP address, and switch port
        based on currently active topology configurations without collision.
        """
        existing_ids = {s.id for s in self.SERVERS}
        existing_ips = {s.ip for s in self.SERVERS} | {self.CLIENT_IP, self.VIRTUAL_IP}
        existing_ports = {s.switch_port for s in self.SERVERS} | {self.CLIENT_SWITCH_PORT}

        # Find next available ID
        idx = 1
        while f"server{idx}" in existing_ids:
            idx += 1
        next_id = f"server{idx}"

        # Find next available IP in 10.0.0.X
        ip_suffix = 2
        while f"10.0.0.{ip_suffix}" in existing_ips:
            ip_suffix += 1
        next_ip = f"10.0.0.{ip_suffix}"

        # Find next available switch port >= 2
        sw_port = 2
        while sw_port in existing_ports:
            sw_port += 1

        return {
            "id": next_id,
            "ip": next_ip,
            "port": 80,
            "switch_port": sw_port,
            "weight": 1,
        }


CONFIG = NetworkConfig()

