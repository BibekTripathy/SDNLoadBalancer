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
    id: str
    server_id: str
    ip: str
    port: int
    switch_port: int = 1
    status: str
    weight: int = 1


class ServerCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=32, description="Unique server identifier (e.g., server4)")
    ip: str = Field(..., description="Unique IPv4 address (e.g., 10.0.0.5)")
    port: int = Field(default=80, ge=1, le=65535, description="HTTP service port")
    switch_port: int = Field(..., ge=2, le=254, description="OVS switch port (>= 2)")
    weight: int = Field(default=1, ge=1, le=100, description="Load balancing capacity weight")


class ServerWeightUpdateRequest(BaseModel):
    weight: int = Field(..., ge=1, le=100, description="Updated weight capacity (>= 1)")


class ServerDetailResponse(BaseModel):
    id: str
    server_id: str
    ip: str
    port: int
    switch_port: int
    status: str
    weight: int = 1
    telemetry: Optional[Dict[str, Any]] = None


class ServerHealthUpdateRequest(BaseModel):
    server_id: str
    status: str = Field(..., description="Target status: HEALTHY, DOWN, DRAINING, or RECOVERING")
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
