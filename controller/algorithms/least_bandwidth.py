"""
Least Bandwidth Load Balancing Algorithm.
"""

from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class LeastBandwidthAlgorithm(BaseLoadBalancerAlgorithm):
    """Directs traffic to the server currently consuming the lowest bandwidth."""

    def __init__(self):
        super().__init__(
            name="least_bandwidth",
            description="Selects the server with the lowest current bandwidth/throughput utilization.",
        )

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        # Extract current bandwidth (e.g. Mbps or bytes/sec) per server from telemetry
        bandwidth_usage = {}
        for s in servers:
            server_metrics = telemetry_data.get(s.id, {})
            # Prefer current_bandwidth_mbps, fallback to tx_bytes or byte_rate
            bandwidth_usage[s.id] = server_metrics.get("bandwidth_mbps", 0.0)

        # Select server with minimum bandwidth usage
        selected = min(servers, key=lambda s: bandwidth_usage.get(s.id, 0.0))

        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "bandwidth_usage": bandwidth_usage,
            "min_bandwidth_mbps": bandwidth_usage[selected.id],
            "reason": f"Server {selected.id} has lowest current bandwidth usage ({bandwidth_usage[selected.id]:.2f} Mbps)",
        }
        return selected, reasoning
