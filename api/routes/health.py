"""
Health check and failure simulation REST endpoints.
"""

from typing import Dict, List
from fastapi import APIRouter, HTTPException

from api.models import ServerHealthUpdateRequest, ServerStatus
from controller.config import CONFIG
from controller.events import ServerHealthState

from api.controller_client import controller_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/status")
async def get_health_status() -> Dict[str, str]:
    """Returns current health state of all backend servers."""
    return controller_client._local_server_health


@router.post("/override")
async def override_server_health(req: ServerHealthUpdateRequest):
    """Simulates a server failure or recovery for demonstration."""
    valid_states = [s.value for s in ServerHealthState]
    if req.status.upper() not in valid_states:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid health state '{req.status}'. Must be one of {valid_states}",
        )
    await controller_client.set_server_health(req.server_id, req.status.upper(), reason=req.reason or "API update")
    return {
        "status": "success",
        "server_id": req.server_id,
        "new_state": req.status.upper(),
        "message": f"Server {req.server_id} status updated to {req.status.upper()}",
    }
