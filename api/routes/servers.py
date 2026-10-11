"""
Backend Server Pool Management Routes.
Supports dynamic server CRUD, draining, weight adjustment, health management,
and WebSocket broadcasting for both live Mininet and simulated topologies.
"""

import logging
import subprocess
import httpx
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status

from api.models import (
    ServerCreateRequest,
    ServerDetailResponse,
    ServerHealthUpdateRequest,
    ServerStatus,
    ServerWeightUpdateRequest,
)
from api.controller_client import controller_client
from api.websocket import ws_manager
from controller.config import CONFIG, BackendServer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["servers"])


def _is_real_mininet_active() -> bool:
    """Checks if real Open vSwitch switch 's1' is present on the Linux host."""
    try:
        res = subprocess.run(
            ["ovs-vsctl", "br-exists", "s1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=1.0,
        )
        return res.returncode == 0
    except Exception:
        return False


async def _verify_real_http_health(ip: str, port: int) -> bool:
    """Probes backend server HTTP service to verify it is responsive."""
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(f"http://{ip}:{port}/")
            return res.status_code == 200
    except Exception:
        return False


@router.get("", response_model=List[ServerStatus])
async def list_servers():
    """Retrieves all registered backend servers."""
    servers_data = await controller_client.get_servers()
    return [
        ServerStatus(
            id=s["id"],
            server_id=s.get("server_id", s["id"]),
            ip=s["ip"],
            port=s.get("port", 80),
            switch_port=s.get("switch_port", 1),
            status=s.get("status", "HEALTHY"),
            weight=s.get("weight", 1),
        )
        for s in servers_data
    ]


@router.get("/suggest")
async def suggest_server_configuration():
    """Calculates non-colliding default ID, IP, and switch port for a new backend."""
    return controller_client.suggest_next_server()


@router.get("/{server_id}", response_model=ServerDetailResponse)
async def get_server_details(server_id: str):
    """Retrieves detailed configuration and live telemetry for a backend server."""
    server = CONFIG.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found in registry",
        )

    telemetry_map = await controller_client.get_telemetry()
    srv_telemetry = telemetry_map.get(server_id, {})
    current_health = controller_client._local_server_health.get(server_id, "HEALTHY")

    return ServerDetailResponse(
        id=server.id,
        server_id=server.id,
        ip=server.ip,
        port=server.port,
        switch_port=server.switch_port,
        status=current_health,
        weight=server.weight,
        telemetry=srv_telemetry,
    )


@router.post("", response_model=ServerStatus, status_code=status.HTTP_201_CREATED)
async def add_server(req: ServerCreateRequest):
    """
    Creates and registers a new backend server into the load balancer pool.
    Enforces validation against duplicate IDs, IP addresses, and switch ports.
    """
    # 1. Validation checks against existing registry
    if CONFIG.get_server(req.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server ID '{req.id}' is already registered",
        )

    if req.ip in [s.ip for s in CONFIG.SERVERS]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"IP address '{req.ip}' is already in use by another backend",
        )

    if req.ip in [CONFIG.CLIENT_IP, CONFIG.VIRTUAL_IP]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IP address '{req.ip}' conflicts with reserved client or virtual IP",
        )

    if req.switch_port == CONFIG.CLIENT_SWITCH_PORT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Switch port {req.switch_port} is reserved for the Client",
        )

    if req.switch_port in [s.switch_port for s in CONFIG.SERVERS]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Switch port {req.switch_port} is already assigned to another backend",
        )

    is_real = _is_real_mininet_active()
    initial_status = "HEALTHY"

    # In real mode, check if the server is actually reachable
    if is_real:
        is_reachable = await _verify_real_http_health(req.ip, req.port)
        if not is_reachable:
            # In real mode, server must be reachable or marked DOWN
            initial_status = "DOWN"
            logger.warning(
                f"Real network detected: backend http://{req.ip}:{req.port}/ is not responding. Registering as DOWN."
            )

    try:
        created = await controller_client.add_server({
            "id": req.id,
            "ip": req.ip,
            "port": req.port,
            "switch_port": req.switch_port,
            "weight": req.weight,
        })
        if is_real and initial_status == "DOWN":
            await controller_client.set_server_health(req.id, "DOWN", reason="HTTP probe failed on create")
            created["status"] = "DOWN"
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Broadcast WebSocket event
    await ws_manager.broadcast({
        "event_type": "SERVER_ADDED",
        "data": {
            "server_id": req.id,
            "ip": req.ip,
            "port": req.port,
            "switch_port": req.switch_port,
            "weight": req.weight,
            "status": initial_status,
            "mode": "real" if is_real else "simulation",
        },
        "summary": f"Backend server {req.id} ({req.ip}) added to pool ({'Real Mininet' if is_real else 'Simulated'})",
    })

    return ServerStatus(
        id=created["id"],
        server_id=created["id"],
        ip=created["ip"],
        port=created["port"],
        switch_port=created["switch_port"],
        status=created["status"],
        weight=created["weight"],
    )


@router.delete("/{server_id}")
async def remove_server(server_id: str):
    """
    Safely removes a backend server from the pool.
    Cleans up OpenFlow rules, telemetry, and connection tracking.
    """
    server = CONFIG.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found in registry",
        )

    try:
        await controller_client.remove_server(server_id)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Broadcast WebSocket event
    await ws_manager.broadcast({
        "event_type": "SERVER_REMOVED",
        "data": {"server_id": server_id, "ip": server.ip},
        "summary": f"Backend server {server_id} removed from load balancer pool",
    })

    return {
        "status": "success",
        "message": f"Server '{server_id}' successfully removed from pool",
        "server_id": server_id,
    }


@router.post("/{server_id}/drain")
async def drain_server(server_id: str):
    """
    Marks a server as DRAINING to stop new connections while letting existing connections finish.
    """
    server = CONFIG.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found in registry",
        )

    await controller_client.drain_server(server_id)

    # Broadcast WebSocket event
    await ws_manager.broadcast({
        "event_type": "SERVER_DRAINING",
        "data": {"server_id": server_id},
        "summary": f"Backend server {server_id} marked as DRAINING",
    })

    return {
        "status": "success",
        "message": f"Server '{server_id}' is now draining active connections",
        "server_id": server_id,
    }


@router.post("/{server_id}/health")
async def update_server_health(server_id: str, req: ServerHealthUpdateRequest):
    """Updates health status (HEALTHY, DOWN, DRAINING, RECOVERING) for a server."""
    server = CONFIG.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found in registry",
        )

    status_upper = req.status.upper()
    valid_states = ["HEALTHY", "DOWN", "DRAINING", "RECOVERING"]
    if status_upper not in valid_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid health state '{req.status}'. Valid states: {valid_states}",
        )

    await controller_client.set_server_health(server_id, status_upper, reason=req.reason or "API update")

    # Broadcast WebSocket event
    await ws_manager.broadcast({
        "event_type": "SERVER_HEALTH_CHANGED",
        "data": {
            "server_id": server_id,
            "new_state": status_upper,
            "reason": req.reason or "API update",
        },
        "summary": f"Server {server_id} health updated to {status_upper}",
    })

    return {
        "status": "success",
        "server_id": server_id,
        "new_state": status_upper,
    }


@router.post("/{server_id}/weight")
async def update_server_weight(server_id: str, req: ServerWeightUpdateRequest):
    """Updates load-balancing weight for a backend server."""
    server = CONFIG.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_id}' not found in registry",
        )

    try:
        await controller_client.update_server_weight(server_id, req.weight)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Broadcast WebSocket event
    await ws_manager.broadcast({
        "event_type": "SERVER_WEIGHT_UPDATED",
        "data": {"server_id": server_id, "weight": req.weight},
        "summary": f"Server {server_id} weight capacity set to {req.weight}",
    })

    return {
        "status": "success",
        "server_id": server_id,
        "weight": req.weight,
    }
