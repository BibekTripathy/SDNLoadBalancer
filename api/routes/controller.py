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
from api.controller_client import controller_client

router = APIRouter(prefix="/api/controller", tags=["controller"])


@router.get("/status", response_model=ControllerStatusResponse)
async def get_controller_status():
    """Returns overall status of the SDN controller and load balancer."""
    status = await controller_client.get_status()
    return ControllerStatusResponse(
        controller_status=status.get("controller_status", "RUNNING"),
        active_algorithm=status.get("active_algorithm", "round_robin"),
        algorithm_description=status.get("algorithm_description", "Sequential round-robin distribution across available servers."),
        total_requests=status.get("total_requests", 0),
        healthy_servers_count=status.get("healthy_servers_count", len(CONFIG.SERVERS)),
        total_servers_count=status.get("total_servers_count", len(CONFIG.SERVERS)),
        virtual_ip=status.get("virtual_ip", CONFIG.VIRTUAL_IP),
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
    await controller_client.set_algorithm(req.algorithm.lower())
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
