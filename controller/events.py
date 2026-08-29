"""
SDN Controller event schemas for telemetry, load balancing, and WebSocket broadcasting.
"""

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    ALGORITHM_CHANGED = "ALGORITHM_CHANGED"
    SERVER_SELECTED = "SERVER_SELECTED"
    FLOW_INSTALLED = "FLOW_INSTALLED"
    PACKET_FORWARDED = "PACKET_FORWARDED"
    SERVER_HEALTH_CHANGED = "SERVER_HEALTH_CHANGED"
    TELEMETRY_UPDATED = "TELEMETRY_UPDATED"


class ServerHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DOWN = "DOWN"
    RECOVERING = "RECOVERING"


@dataclass
class ControllerEvent:
    """Standardized event emitted by the SDN controller."""
    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["event_type"] = self.event_type.value
        return result
