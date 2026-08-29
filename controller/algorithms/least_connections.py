"""
Least Connections Load Balancing Algorithm.
"""

from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class LeastConnectionsAlgorithm(BaseLoadBalancerAlgorithm):
    """Directs traffic to the server with the fewest active TCP/flow connections."""

    def __init__(self):
        super().__init__(
            name="least_connections",
            description="Selects the server currently handling the fewest active connections.",
        )

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        # Extract active connection count per server from telemetry
        connection_counts = {}
        for s in servers:
            server_metrics = telemetry_data.get(s.id, {})
            connection_counts[s.id] = server_metrics.get("active_connections", 0)

        # Find server with minimum active connections
        selected = min(servers, key=lambda s: connection_counts.get(s.id, 0))

        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "connection_counts": connection_counts,
            "min_connections": connection_counts[selected.id],
            "reason": f"Server {selected.id} has least active connections ({connection_counts[selected.id]})",
        }
        return selected, reasoning
