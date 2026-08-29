"""
Real-time Network Telemetry and Statistics Collector for Ryu Controller.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from controller.config import CONFIG, BackendServer

logger = logging.getLogger(__name__)


@dataclass
class ServerTelemetry:
    """Live metrics tracked per backend server."""
    server_id: str
    switch_port: int
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    bandwidth_mbps: float = 0.0
    packet_rate: float = 0.0
    active_connections: int = 0
    latency_ms: float = 0.0
    packet_loss_ratio: float = 0.0
    last_updated: float = field(default_factory=time.time)


class TelemetryCollector:
    """Collects and calculates real-time telemetry metrics from OpenFlow statistics."""

    def __init__(self, servers: List[BackendServer]):
        self.servers_by_port: Dict[int, BackendServer] = {s.switch_port: s for s in servers}
        self.servers_by_id: Dict[str, BackendServer] = {s.id: s for s in servers}
        
        # Telemetry storage
        self.metrics: Dict[str, ServerTelemetry] = {
            s.id: ServerTelemetry(server_id=s.id, switch_port=s.switch_port)
            for s in servers
        }
        self._prev_stats: Dict[int, Dict[str, Any]] = {}

    def update_port_stats(self, port_stats_list: list) -> None:
        """Processes OFPPortStats replies to update bandwidth and throughput metrics."""
        now = time.time()
        for stat in port_stats_list:
            port_no = stat.port_no
            if port_no not in self.servers_by_port:
                continue

            server = self.servers_by_port[port_no]
            sid = server.id
            cur_tx = stat.tx_bytes
            cur_rx = stat.rx_bytes
            cur_tx_pkts = stat.tx_packets
            cur_rx_pkts = stat.rx_packets

            prev = self._prev_stats.get(port_no)
            if prev:
                dt = max(now - prev["timestamp"], 0.001)
                delta_bytes = (cur_tx - prev["tx_bytes"]) + (cur_rx - prev["rx_bytes"])
                delta_pkts = (cur_tx_pkts - prev["tx_packets"]) + (cur_rx_pkts - prev["rx_packets"])
                
                # Compute Mbps and packet rate
                mbps = max((delta_bytes * 8) / (dt * 1_000_000.0), 0.0)
                pkt_rate = max(delta_pkts / dt, 0.0)
            else:
                mbps = 0.0
                pkt_rate = 0.0

            # Store updated telemetry
            self.metrics[sid].rx_bytes = cur_rx
            self.metrics[sid].tx_bytes = cur_tx
            self.metrics[sid].rx_packets = cur_rx_pkts
            self.metrics[sid].tx_packets = cur_tx_pkts
            self.metrics[sid].rx_errors = stat.rx_errors
            self.metrics[sid].tx_errors = stat.tx_errors
            self.metrics[sid].bandwidth_mbps = round(mbps, 3)
            self.metrics[sid].packet_rate = round(pkt_rate, 2)
            self.metrics[sid].last_updated = now

            self._prev_stats[port_no] = {
                "timestamp": now,
                "tx_bytes": cur_tx,
                "rx_bytes": cur_rx,
                "tx_packets": cur_tx_pkts,
                "rx_packets": cur_rx_pkts,
            }

    def update_active_connections(self, server_id: str, delta: int) -> None:
        """Increments or decrements active connection count for a server."""
        if server_id in self.metrics:
            current = self.metrics[server_id].active_connections
            self.metrics[server_id].active_connections = max(0, current + delta)

    def set_server_latency(self, server_id: str, latency_ms: float) -> None:
        """Updates measured or synthetic round-trip latency in ms."""
        if server_id in self.metrics:
            self.metrics[server_id].latency_ms = round(latency_ms, 2)

    def set_packet_loss_ratio(self, server_id: str, loss_ratio: float) -> None:
        """Updates measured or synthetic packet loss ratio (0.0 - 1.0)."""
        if server_id in self.metrics:
            self.metrics[server_id].packet_loss_ratio = round(max(0.0, min(1.0, loss_ratio)), 4)

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Returns current snapshot of all server metrics as raw dicts."""
        return {
            sid: {
                "server_id": m.server_id,
                "switch_port": m.switch_port,
                "bandwidth_mbps": m.bandwidth_mbps,
                "packet_rate": m.packet_rate,
                "active_connections": m.active_connections,
                "latency_ms": m.latency_ms,
                "packet_loss_ratio": m.packet_loss_ratio,
                "rx_bytes": m.rx_bytes,
                "tx_bytes": m.tx_bytes,
                "rx_packets": m.rx_packets,
                "tx_packets": m.tx_packets,
                "rx_errors": m.rx_errors,
                "tx_errors": m.tx_errors,
                "last_updated": m.last_updated,
            }
            for sid, m in self.metrics.items()
        }
