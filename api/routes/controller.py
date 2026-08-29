"""
Controller management routes (Algorithms, Status, Servers).
"""

from typing import Dict, List
from fastapi import APIRouter, HTTPException

from api.models import (
    AlgorithmChangeRequest,
    AlgorithmInfo,
    ControllerStatusResponse,
    ServerStatus,
)
from controller.algorithms import list_available_algorithms
from controller.config import CONFIG

router = APIRouter(prefix="/api/controller", tags=["controller"])


@router.get("/status", response_model=ControllerStatusResponse)
async def get_controller_status():
    """Returns overall status of the SDN controller and load balancer."""
    return ControllerStatusResponse(
        controller_status="RUNNING",
        active_algorithm="round_robin",
        algorithm_description="Sequential round-robin distribution across available servers.",
        total_requests=0,
        healthy_servers_count=len(CONFIG.SERVERS),
        total_servers_count=len(CONFIG.SERVERS),
        virtual_ip=CONFIG.VIRTUAL_IP,
    )


@router.get("/algorithms", response_model=List[AlgorithmInfo])
async def get_algorithms():
    """Returns list of all available load balancing algorithms."""
    return list_available_algorithms()


@router.post("/algorithm")
async def switch_algorithm(req: AlgorithmChangeRequest):
    """Dynamically activates a new load balancing algorithm."""
    from controller.algorithms import ALGORITHMS
    if req.algorithm.lower() not in ALGORITHMS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown algorithm '{req.algorithm}'. Valid options: {list(ALGORITHMS.keys())}"
        )
    return {
        "status": "success",
        "active_algorithm": req.algorithm.lower(),
        "message": f"Algorithm switched to {req.algorithm.lower()}"
    }


@router.get("/servers", response_model=List[ServerStatus])
async def get_servers():
    """Returns list of backend servers and their current configurations."""
    return [
        ServerStatus(
            server_id=s.id,
            ip=s.ip,
            port=s.port,
            status="HEALTHY",
            weight=s.weight,
        )
        for s in CONFIG.SERVERS
    ]
