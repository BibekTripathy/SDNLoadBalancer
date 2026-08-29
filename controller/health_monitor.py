"""
Server Health Monitor for SDN Dynamic Load Balancer.

Maintains health state (HEALTHY, DOWN, RECOVERING) and supports runtime simulation
of server failures and recovery for demonstrations.
"""

import logging
import time
from typing import Callable, Dict, List, Optional

from controller.config import BackendServer
from controller.events import ControllerEvent, EventType, ServerHealthState

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors server availability and provides dynamic health management."""

    def __init__(
        self,
        servers: List[BackendServer],
        event_callback: Optional[Callable[[ControllerEvent], None]] = None,
    ):
        self.servers = {s.id: s for s in servers}
        self.health_states: Dict[str, ServerHealthState] = {
            s.id: ServerHealthState.HEALTHY for s in servers
        }
        self.event_callback = event_callback
        self.last_check_time: float = time.time()

    def get_healthy_servers(self) -> List[BackendServer]:
        """Returns the list of servers currently in HEALTHY state."""
        return [
            s for s in self.servers.values()
            if self.health_states[s.id] == ServerHealthState.HEALTHY
        ]

    def get_server_state(self, server_id: str) -> ServerHealthState:
        """Returns current health state of a given server."""
        return self.health_states.get(server_id, ServerHealthState.DOWN)

    def set_server_state(
        self, server_id: str, new_state: ServerHealthState, reason: str = ""
    ) -> None:
        """Manually or dynamically changes the health status of a server."""
        if server_id not in self.servers:
            raise ValueError(f"Unknown server ID: {server_id}")

        old_state = self.health_states[server_id]
        if old_state != new_state:
            self.health_states[server_id] = new_state
            logger.info(
                f"Server {server_id} health changed: {old_state.value} -> {new_state.value} ({reason})"
            )
            if self.event_callback:
                event = ControllerEvent(
                    event_type=EventType.SERVER_HEALTH_CHANGED,
                    data={
                        "server_id": server_id,
                        "old_state": old_state.value,
                        "new_state": new_state.value,
                        "reason": reason,
                    },
                    summary=f"Server {server_id} is now {new_state.value}",
                )
                self.event_callback(event)

    def get_all_health_statuses(self) -> Dict[str, Dict[str, str]]:
        """Returns the status map for all configured servers."""
        return {
            sid: {
                "server_id": sid,
                "ip": self.servers[sid].ip,
                "port": self.servers[sid].port,
                "status": state.value,
            }
            for sid, state in self.health_states.items()
        }
