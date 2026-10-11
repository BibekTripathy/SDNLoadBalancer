"""
Telemetry and metrics REST endpoints.
"""

from typing import Any, Dict
from fastapi import APIRouter
from controller.config import CONFIG

from api.controller_client import controller_client

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Returns current telemetry metrics for all backend servers."""
    return await controller_client.get_telemetry()
