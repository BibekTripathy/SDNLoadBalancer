from api.routes.controller import router as controller_router
from api.routes.health import router as health_router
from api.routes.telemetry import router as telemetry_router
from api.routes.servers import router as servers_router

__all__ = ["controller_router", "health_router", "telemetry_router", "servers_router"]

