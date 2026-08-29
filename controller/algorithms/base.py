"""
Base class for Load Balancing Algorithms.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from controller.config import BackendServer


class BaseLoadBalancerAlgorithm(ABC):
    """Abstract Base Class for all dynamic/static load balancing algorithms."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        """
        Selects a target backend server from active pool.

        Args:
            servers: List of available healthy backend servers.
            client_info: Dictionary containing client IP, port, protocol, etc.
            telemetry_data: Current telemetry metrics for servers (connections, bandwidth, latency, etc.)

        Returns:
            Tuple of (selected BackendServer, decision_metadata_dict)
        """
        pass
