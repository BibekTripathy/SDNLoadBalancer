"""
Controller Client for communicating between FastAPI and the Ryu SDN Controller.
Provides fallback mechanisms if the Ryu controller process is unreachable.
"""

import logging
import httpx
from typing import Any, Dict, List, Optional

from controller.config import CONFIG
from controller.algorithms import ALGORITHMS

logger = logging.getLogger(__name__)

RYU_IPC_URL = "http://127.0.0.1:8088"


class ControllerClient:
    """HTTP client bridge communicating with the internal Ryu IPC endpoint."""

    def __init__(self, base_url: str = RYU_IPC_URL):
        self.base_url = base_url
        self._local_active_algorithm: str = "round_robin"
        self._local_server_health: Dict[str, str] = {s.id: "HEALTHY" for s in CONFIG.SERVERS}
        self._local_total_requests: int = 0

    async def is_available(self) -> bool:
        """Checks if the Ryu SDN controller IPC endpoint is reachable."""
        try:
            async with httpx.AsyncClient(timeout=0.6) as client:
                res = await client.get(f"{self.base_url}/status")
                return res.status_code == 200
        except Exception:
            return False

    async def get_status(self) -> Dict[str, Any]:
        """Retrieves controller status from Ryu or returns local state."""
        try:
            async with httpx.AsyncClient(timeout=0.8) as client:
                res = await client.get(f"{self.base_url}/status")
                if res.status_code == 200:
                    data = res.json()
                    self._local_active_algorithm = data.get("active_algorithm", self._local_active_algorithm)
                    self._local_total_requests = data.get("total_requests", self._local_total_requests)
                    return data
        except Exception as e:
            logger.debug(f"Ryu IPC unreachable ({e}), using local status fallback")

        algo_cls = ALGORITHMS.get(self._local_active_algorithm)
        algo_desc = algo_cls().description if algo_cls else "Sequential distribution"
        healthy_count = sum(1 for status in self._local_server_health.values() if status == "HEALTHY")

        return {
            "controller_status": "OFFLINE_SIMULATION",
            "active_algorithm": self._local_active_algorithm,
            "algorithm_description": algo_desc,
            "total_requests": self._local_total_requests,
            "healthy_servers_count": healthy_count,
            "total_servers_count": len(CONFIG.SERVERS),
            "virtual_ip": CONFIG.VIRTUAL_IP,
            "telemetry": self.get_default_telemetry(),
        }

    async def set_algorithm(self, algorithm_name: str) -> bool:
        """Instructs Ryu controller to activate a new load balancing algorithm."""
        self._local_active_algorithm = algorithm_name.lower()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(
                    f"{self.base_url}/algorithm",
                    json={"algorithm": algorithm_name.lower()},
                )
                return res.status_code == 200
        except Exception as e:
            logger.debug(f"Could not notify Ryu of algorithm change: {e}")
            return False

    async def set_server_health(self, server_id: str, status: str, reason: str = "") -> bool:
        """Instructs Ryu controller to update health status for a backend server."""
        self._local_server_health[server_id] = status.upper()
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(
                    f"{self.base_url}/health",
                    json={"server_id": server_id, "status": status.upper(), "reason": reason},
                )
                return res.status_code == 200
        except Exception as e:
            logger.debug(f"Could not notify Ryu of health change: {e}")
            return False

    async def reset_connection_tracking(self) -> bool:
        """Resets Ryu controller connection tracker between benchmark experiments."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.post(f"{self.base_url}/reset_flows")
                return res.status_code == 200
        except Exception:
            return False

    async def get_telemetry(self) -> Dict[str, Any]:
        """Retrieves live OpenFlow telemetry metrics from Ryu."""
        try:
            async with httpx.AsyncClient(timeout=0.8) as client:
                res = await client.get(f"{self.base_url}/telemetry")
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass
        return self.get_default_telemetry()

    def get_default_telemetry(self) -> Dict[str, Dict[str, Any]]:
        """Returns baseline telemetry schema for all servers."""
        return {
            s.id: {
                "server_id": s.id,
                "switch_port": s.switch_port,
                "bandwidth_mbps": 0.0,
                "packet_rate": 0.0,
                "active_connections": 0,
                "latency_ms": 1.5,
                "packet_loss_ratio": 0.0,
                "rx_bytes": 0,
                "tx_bytes": 0,
                "rx_packets": 0,
                "tx_packets": 0,
            }
            for s in CONFIG.SERVERS
        }


controller_client = ControllerClient()
