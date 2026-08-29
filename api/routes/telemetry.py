"""
Telemetry and metrics REST endpoints.
"""

from typing import Any, Dict
from fastapi import APIRouter
from controller.config import CONFIG

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Returns current telemetry metrics for all backend servers."""
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
