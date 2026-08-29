"""
FastAPI Application Entry Point & WebSocket Gateway.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import controller_router, health_router, telemetry_router
from api.websocket import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SDN Load Balancer API Gateway starting up...")
    yield
    logger.info("SDN Load Balancer API Gateway shutting down...")


app = FastAPI(
    title="SDN Dynamic Load Balancer API",
    description="REST & WebSocket API Gateway for Ryu SDN Controller and Network Operations Dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for React dashboard development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(controller_router)
app.include_router(health_router)
app.include_router(telemetry_router)


@app.get("/")
async def root():
    return {
        "name": "SDN Dynamic Load Balancer Gateway",
        "status": "online",
        "docs": "/docs",
        "websocket": "/ws/events",
    }


@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time event stream for React frontend dashboard."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for any client messages/heartbeats
            data = await websocket.receive_text()
            # Echo or process client command if needed
            await websocket.send_json({"type": "PONG", "payload": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as err:
        logger.error(f"WebSocket error: {err}")
        ws_manager.disconnect(websocket)
