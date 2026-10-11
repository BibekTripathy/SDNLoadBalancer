"""
Pydantic Models and Data Schemas for the SDN Benchmarking Laboratory.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from controller.algorithms import ALGORITHMS
from controller.config import CONFIG


class BenchmarkLifecycleState(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureScenario(BaseModel):
    """Optional failure and recovery injection during a benchmark run."""
    server_id: str = Field(..., description="Server to simulate failure on")
    at_second: float = Field(..., ge=1.0, description="Elapsed test second when server fails")
    recover_at_second: Optional[float] = Field(None, ge=1.0, description="Elapsed second when server recovers")


class BenchmarkConfig(BaseModel):
    """Configuration parameters for a multi-algorithm benchmark experiment."""
    name: str = Field("SDN Load Balancing Benchmark", description="Descriptive name of the benchmark experiment")
    algorithms: List[str] = Field(
        default=["round_robin", "least_connections", "weighted_round_robin"],
        min_length=1,
        description="List of algorithms to evaluate sequentially",
    )
    rate: int = Field(20, ge=1, le=500, description="Target requests per second (RPS)")
    concurrency: int = Field(4, ge=1, le=50, description="Concurrent request workers")
    duration: int = Field(10, ge=3, le=120, description="Duration in seconds per algorithm test run")
    warmup_duration: int = Field(2, ge=0, le=30, description="Warm-up seconds (excluded from final statistics)")
    repetitions: int = Field(1, ge=1, le=5, description="Number of repetitions per algorithm configuration")
    target_url: str = Field(
        f"http://{CONFIG.VIRTUAL_IP}:80/",
        description="Target Virtual IP HTTP endpoint for traffic generation",
    )
    inject_latency_ms: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional synthetic server latency in ms to inject (e.g. {'server2': 25.0})",
    )
    failure_scenario: Optional[FailureScenario] = Field(
        default=None,
        description="Optional server failure and recovery injection scenario",
    )

    @field_validator("algorithms")
    @classmethod
    def validate_algorithms(cls, v: List[str]) -> List[str]:
        valid_algos = set(ALGORITHMS.keys())
        normalized = []
        for algo in v:
            clean = algo.strip().lower()
            if clean not in valid_algos:
                raise ValueError(f"Unknown algorithm '{algo}'. Valid options: {list(valid_algos)}")
            if clean not in normalized:
                normalized.append(clean)
        if not normalized:
            raise ValueError("At least one valid algorithm must be selected")
        return normalized

    @field_validator("warmup_duration")
    @classmethod
    def validate_warmup(cls, v: int, info) -> int:
        duration = info.data.get("duration", 10)
        if v >= duration:
            raise ValueError(f"Warm-up duration ({v}s) must be strictly less than total duration ({duration}s)")
        return v


class RunMetrics(BaseModel):
    """Detailed measurements collected for a single algorithm repetition."""
    algorithm: str
    repetition: int
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    error_rate_pct: float = 0.0
    achieved_rps: float = 0.0
    throughput_mbps: float = 0.0
    mean_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    status_codes: Dict[str, int] = Field(default_factory=dict)
    timeouts: int = 0
    backend_distribution: Dict[str, int] = Field(default_factory=dict)
    backend_distribution_pct: Dict[str, float] = Field(default_factory=dict)
    jains_fairness_index: float = 1.0
    recovery_time_sec: Optional[float] = None
    is_simulated: bool = False
    time_series: List[Dict[str, Any]] = Field(default_factory=list)


class AlgorithmSummary(BaseModel):
    """Aggregated steady-state performance summary across all repetitions of an algorithm."""
    algorithm: str
    repetition_count: int
    mean_achieved_rps: float
    mean_latency_ms: float
    p95_latency_ms: float
    mean_error_rate_pct: float
    mean_throughput_mbps: float
    aggregate_distribution: Dict[str, int]
    jains_fairness_index: float
    recovery_time_sec: Optional[float] = None
    is_simulated: bool = False


class BenchmarkLiveStats(BaseModel):
    """Real-time intermediate progress metrics broadcast via WebSocket."""
    requests_sent: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    current_rps: float = 0.0
    current_latency_ms: float = 0.0
    current_active_server: Optional[str] = None


class BenchmarkDetails(BaseModel):
    """Full representation of a benchmark experiment including status, runs, and summaries."""
    id: str
    name: str
    created_at: str
    status: BenchmarkLifecycleState
    config: BenchmarkConfig
    current_algorithm: Optional[str] = None
    current_repetition: Optional[int] = None
    elapsed_seconds: float = 0.0
    total_estimated_seconds: float = 0.0
    progress_percent: float = 0.0
    live_stats: BenchmarkLiveStats = Field(default_factory=BenchmarkLiveStats)
    runs: List[RunMetrics] = Field(default_factory=list)
    summary: List[AlgorithmSummary] = Field(default_factory=list)
    error_message: Optional[str] = None
    is_simulated: bool = False


class BenchmarkListItem(BaseModel):
    """Concise representation of a benchmark run for history listing."""
    id: str
    name: str
    created_at: str
    status: BenchmarkLifecycleState
    algorithms: List[str]
    total_runs: int
    is_simulated: bool
