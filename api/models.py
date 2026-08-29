"""
Pydantic Models for FastAPI REST API & WebSocket schemas.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlgorithmChangeRequest(BaseModel):
    algorithm: str = Field(..., description="Name of the load balancing algorithm to activate")


class AlgorithmInfo(BaseModel):
    id: str
    name: str
    description: str


class ServerStatus(BaseModel):
    server_id: str
    ip: str
    port: int
    status: str
    weight: int = 1


class ServerHealthUpdateRequest(BaseModel):
    server_id: str
    status: str = Field(..., description="Target status: HEALTHY, DOWN, or RECOVERING")
    reason: Optional[str] = "Manual update via API"


class TelemetryMetrics(BaseModel):
    server_id: str
    switch_port: int
    bandwidth_mbps: float
    packet_rate: float
    active_connections: int
    latency_ms: float
    packet_loss_ratio: float
    rx_bytes: int
    tx_bytes: int
    rx_packets: int
    tx_packets: int
    last_updated: float


class ControllerStatusResponse(BaseModel):
    controller_status: str
    active_algorithm: str
    algorithm_description: str
    total_requests: int
    healthy_servers_count: int
    total_servers_count: int
    virtual_ip: str
