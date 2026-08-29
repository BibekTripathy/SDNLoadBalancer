"""
Round Robin Load Balancing Algorithm.
"""

from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class RoundRobinAlgorithm(BaseLoadBalancerAlgorithm):
    """Distributes incoming requests sequentially among available backend servers."""

    def __init__(self):
        super().__init__(
            name="round_robin",
            description="Sequential round-robin distribution across available servers.",
        )
        self.current_index = 0

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        idx = self.current_index % len(servers)
        selected = servers[idx]
        self.current_index = (idx + 1) % len(servers)

        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "server_index": idx,
            "total_healthy_servers": len(servers),
            "reason": f"Round Robin selected index {idx} ({selected.id})",
        }
        return selected, reasoning
