"""
Adaptive / Composite Load Balancing Algorithm.
"""

from typing import Any, Dict, List, Tuple

from controller.algorithms.base import BaseLoadBalancerAlgorithm
from controller.config import BackendServer


class AdaptiveAlgorithm(BaseLoadBalancerAlgorithm):
    """
    Computes a composite telemetry-based load score per server:
      score = (w_bw * norm_bw) + (w_conn * norm_conn) + (w_lat * norm_lat) + (w_loss * norm_loss)
    Selects the backend with the lowest score.
    """

    def __init__(
        self,
        weight_bandwidth: float = 0.4,
        weight_connections: float = 0.3,
        weight_latency: float = 0.2,
        weight_loss: float = 0.1,
    ):
        super().__init__(
            name="adaptive",
            description="Real-time multi-metric composite scoring (bandwidth, connections, latency, loss).",
        )
        self.w_bw = weight_bandwidth
        self.w_conn = weight_connections
        self.w_lat = weight_latency
        self.w_loss = weight_loss

    def _normalize(self, values: Dict[str, float]) -> Dict[str, float]:
        """Normalizes dictionary of metric values between 0.0 and 1.0."""
        max_val = max(values.values()) if values else 0.0
        min_val = min(values.values()) if values else 0.0
        
        if max_val == min_val:
            # If all values are equal, normalized score is 0.0 for all
            return {k: 0.0 for k in values}
        
        range_val = max_val - min_val
        return {k: (v - min_val) / range_val for k, v in values.items()}

    def select_server(
        self,
        servers: List[BackendServer],
        client_info: Dict[str, Any],
        telemetry_data: Dict[str, Any],
    ) -> Tuple[BackendServer, Dict[str, Any]]:
        if not servers:
            raise ValueError("No healthy backend servers available")

        # Collect raw metrics for each server
        raw_bw: Dict[str, float] = {}
        raw_conn: Dict[str, float] = {}
        raw_lat: Dict[str, float] = {}
        raw_loss: Dict[str, float] = {}

        for s in servers:
            metrics = telemetry_data.get(s.id, {})
            raw_bw[s.id] = float(metrics.get("bandwidth_mbps", 0.0))
            raw_conn[s.id] = float(metrics.get("active_connections", 0.0))
            raw_lat[s.id] = float(metrics.get("latency_ms", 0.0))
            raw_loss[s.id] = float(metrics.get("packet_loss_ratio", 0.0))

        # Normalize metrics across active server pool
        norm_bw = self._normalize(raw_bw)
        norm_conn = self._normalize(raw_conn)
        norm_lat = self._normalize(raw_lat)
        norm_loss = self._normalize(raw_loss)

        # Calculate composite score per server
        scores: Dict[str, float] = {}
        breakdowns: Dict[str, Dict[str, float]] = {}

        for s in servers:
            sid = s.id
            bw_part = self.w_bw * norm_bw[sid]
            conn_part = self.w_conn * norm_conn[sid]
            lat_part = self.w_lat * norm_lat[sid]
            loss_part = self.w_loss * norm_loss[sid]
            composite_score = bw_part + conn_part + lat_part + loss_part

            scores[sid] = composite_score
            breakdowns[sid] = {
                "raw_bandwidth_mbps": raw_bw[sid],
                "raw_connections": raw_conn[sid],
                "raw_latency_ms": raw_lat[sid],
                "raw_packet_loss_ratio": raw_loss[sid],
                "norm_bandwidth": norm_bw[sid],
                "norm_connections": norm_conn[sid],
                "norm_latency": norm_lat[sid],
                "norm_packet_loss": norm_loss[sid],
                "composite_score": round(composite_score, 4),
            }

        # Choose the server with lowest composite score
        selected = min(servers, key=lambda s: scores[s.id])

        reasoning = {
            "algorithm": self.name,
            "selected_server": selected.id,
            "selected_score": round(scores[selected.id], 4),
            "weights": {
                "bandwidth": self.w_bw,
                "connections": self.w_conn,
                "latency": self.w_lat,
                "packet_loss": self.w_loss,
            },
            "scores": {k: round(v, 4) for k, v in scores.items()},
            "breakdowns": breakdowns,
            "reason": (
                f"Adaptive algorithm selected {selected.id} with lowest composite score "
                f"({scores[selected.id]:.4f})"
            ),
        }
        return selected, reasoning
