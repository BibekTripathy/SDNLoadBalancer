"""
Core Load Balancer Engine for SDN Controller.

Integrates active load balancing algorithms, telemetry inputs, and server health tracking.
"""

import logging
import time
from ryu.lib import hub
from typing import Any, Callable, Dict, List, Optional, Tuple

from controller.algorithms import BaseLoadBalancerAlgorithm, get_algorithm
from controller.config import CONFIG, BackendServer
from controller.events import ControllerEvent, EventType
from controller.health_monitor import HealthMonitor
from controller.telemetry import TelemetryCollector

logger = logging.getLogger(__name__)


class LoadBalancerEngine:
    """Core coordinator for SDN Load Balancing decisions."""

    def __init__(
        self,
        telemetry: TelemetryCollector,
        health_monitor: HealthMonitor,
        default_algorithm: str = "round_robin",
        event_callback: Optional[Callable[[ControllerEvent], None]] = None,
    ):
        self.telemetry = telemetry
        self.health_monitor = health_monitor
        self.active_algorithm: BaseLoadBalancerAlgorithm = get_algorithm(default_algorithm)
        self.event_callback = event_callback
        self.total_requests: int = 0
        
        # Connection tracking table to prevent SDN FlowMod race conditions.
        # Maps (client_ip, client_port) -> (BackendServer, timestamp)
        self.active_connections: Dict[Tuple[str, int], Tuple[BackendServer, float]] = {}
        
        # Start background cleanup task
        self.cleanup_thread = hub.spawn(self._cleanup_stale_connections)

    def _cleanup_stale_connections(self):
        """Periodically removes stale connection tracking entries."""
        while True:
            now = time.time()
            stale_keys = [
                k for k, (server, ts) in self.active_connections.items()
                if now - ts > 60.0  # 60 second connection tracker timeout
            ]
            for k in stale_keys:
                del self.active_connections[k]
                
            hub.sleep(30.0)

    def set_algorithm(self, algorithm_name: str) -> None:
        """Dynamically switches active load balancing algorithm at runtime."""
        old_algo = self.active_algorithm.name
        self.active_algorithm = get_algorithm(algorithm_name)
        logger.info(f"Algorithm switched: {old_algo} -> {self.active_algorithm.name}")

        if self.event_callback:
            event = ControllerEvent(
                event_type=EventType.ALGORITHM_CHANGED,
                data={
                    "old_algorithm": old_algo,
                    "new_algorithm": self.active_algorithm.name,
                    "description": self.active_algorithm.description,
                },
                summary=f"Algorithm changed to {self.active_algorithm.name}",
            )
            self.event_callback(event)

    def select_backend(
        self, client_info: Dict[str, Any]
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        """
        Evaluates active algorithm on healthy servers and returns chosen backend + reasoning.
        """
        # 1. Check if this is an existing connection to avoid breaking TCP handshakes
        client_ip = client_info.get("client_ip")
        client_port = client_info.get("client_port")
        if client_ip and client_port:
            conn_key = (client_ip, client_port)
            if conn_key in self.active_connections:
                saved_server, _ = self.active_connections[conn_key]
                # Refresh timestamp
                self.active_connections[conn_key] = (saved_server, time.time())
                return saved_server, "Existing connection"

        healthy_servers = self.health_monitor.get_healthy_servers()
        if not healthy_servers:
            raise RuntimeError("No healthy backend servers are currently available")

        telemetry_snapshot = self.telemetry.get_all_metrics()
        self.total_requests += 1

        selected_server, reasoning = self.active_algorithm.select_server(
            servers=healthy_servers,
            client_info=client_info,
            telemetry_data=telemetry_snapshot,
        )

        # 2. Save the assignment in our connection tracker
        if client_ip and client_port:
            self.active_connections[(client_ip, client_port)] = (selected_server, time.time())

        if self.event_callback:
            event = ControllerEvent(
                event_type=EventType.SERVER_SELECTED,
                data={
                    "request_id": self.total_requests,
                    "client_info": client_info,
                    "selected_server": selected_server.id,
                    "selected_server_ip": selected_server.ip,
                    "reasoning": reasoning,
                },
                summary=f"Selected {selected_server.id} via {self.active_algorithm.name}",
            )
            self.event_callback(event)

        return selected_server, reasoning
