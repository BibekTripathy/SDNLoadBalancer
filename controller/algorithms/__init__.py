"""
Algorithm registry and dynamic factory.
"""

from typing import Dict, List, Type

from controller.algorithms.adaptive import AdaptiveAlgorithm
from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.algorithms.least_bandwidth import LeastBandwidthAlgorithm
from controller.algorithms.least_connections import LeastConnectionsAlgorithm
from controller.algorithms.random_lb import RandomAlgorithm
from controller.algorithms.round_robin import RoundRobinAlgorithm
from controller.algorithms.weighted_round_robin import WeightedRoundRobinAlgorithm

ALGORITHMS: Dict[str, Type[BaseLoadBalancerAlgorithm]] = {
    "round_robin": RoundRobinAlgorithm,
    "random": RandomAlgorithm,
    "least_connections": LeastConnectionsAlgorithm,
    "least_bandwidth": LeastBandwidthAlgorithm,
    "weighted_round_robin": WeightedRoundRobinAlgorithm,
    "adaptive": AdaptiveAlgorithm,
}


def get_algorithm(name: str) -> BaseLoadBalancerAlgorithm:
    """Factory function to instantiate an algorithm by name."""
    algo_class = ALGORITHMS.get(name.lower())
    if not algo_class:
        raise ValueError(
            f"Unknown algorithm '{name}'. Available options: {list(ALGORITHMS.keys())}"
        )
    return algo_class()


def list_available_algorithms() -> List[Dict[str, str]]:
    """Returns metadata for all available algorithms."""
    result = []
    for name, cls in ALGORITHMS.items():
        instance = cls()
        result.append({
            "id": name,
            "name": instance.name,
            "description": instance.description,
        })
    return result


__all__ = [
    "BaseLoadBalancerAlgorithm",
    "RoundRobinAlgorithm",
    "RandomAlgorithm",
    "LeastConnectionsAlgorithm",
    "LeastBandwidthAlgorithm",
    "WeightedRoundRobinAlgorithm",
    "AdaptiveAlgorithm",
    "ALGORITHMS",
    "get_algorithm",
    "list_available_algorithms",
]
