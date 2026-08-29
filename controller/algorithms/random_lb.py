"""
Random Load Balancing Algorithm.
"""

import random
from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class RandomAlgorithm(BaseLoadBalancerAlgorithm):
    """Distributes incoming requests uniformly at random among available backend servers."""

    def __init__(self):
        super().__init__(
            name="random",
            description="Uniform random selection across available healthy servers.",
        )

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        selected = random.choice(servers)
        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "total_healthy_servers": len(servers),
            "reason": f"Random selection chose {selected.id}",
        }
        return selected, reasoning
