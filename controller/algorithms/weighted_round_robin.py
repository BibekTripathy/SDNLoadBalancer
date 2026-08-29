"""
Weighted Round Robin Load Balancing Algorithm.
"""

from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class WeightedRoundRobinAlgorithm(BaseLoadBalancerAlgorithm):
    """Distributes incoming requests proportional to server weights."""

    def __init__(self):
        super().__init__(
            name="weighted_round_robin",
            description="Round robin weighted by server capacity/weight configuration.",
        )
        self.current_index = -1
        self.current_weight = 0

    def _get_max_weight(self, servers: List[BackendServer]) -> int:
        return max((s.weight for s in servers), default=1)

    def _get_gcd_weights(self, servers: List[BackendServer]) -> int:
        import math
        weights = [s.weight for s in servers if s.weight > 0]
        if not weights:
            return 1
        gcd = weights[0]
        for w in weights[1:]:
            gcd = math.gcd(gcd, w)
        return gcd

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        max_weight = self._get_max_weight(servers)
        gcd_weight = self._get_gcd_weights(servers)
        num_servers = len(servers)

        while True:
            self.current_index = (self.current_index + 1) % num_servers
            if self.current_index == 0:
                self.current_weight = self.current_weight - gcd_weight
                if self.current_weight <= 0:
                    self.current_weight = max_weight
                    if self.current_weight == 0:
                        selected = servers[0]
                        break
            if servers[self.current_index].weight >= self.current_weight:
                selected = servers[self.current_index]
                break

        weights_map = {s.id: s.weight for s in servers}
        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "server_weight": selected.weight,
            "weights": weights_map,
            "reason": f"Weighted Round Robin selected {selected.id} (weight={selected.weight})",
        }
        return selected, reasoning
