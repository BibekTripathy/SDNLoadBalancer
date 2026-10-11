"""
Benchmark Engine managing the complete experiment lifecycle:
Validation -> Preparing -> Running -> Completed / Failed / Cancelled -> Post-run Cleanup.
Broadcasts real-time events over WebSockets and saves results into SQLite.
"""

import asyncio
import datetime
import logging
import uuid
from typing import Dict, List, Optional

from api.benchmark.generator import WorkloadGenerator
from api.benchmark.metrics import aggregate_runs
from api.benchmark.models import (
    AlgorithmSummary,
    BenchmarkConfig,
    BenchmarkDetails,
    BenchmarkLifecycleState,
    BenchmarkLiveStats,
    RunMetrics,
)
from api.benchmark.storage import benchmark_storage
from api.controller_client import controller_client
from api.websocket import ws_manager
from controller.config import CONFIG

logger = logging.getLogger(__name__)


class BenchmarkEngine:
    """Singleton service managing concurrent benchmark safety and execution lifecycle."""

    def __init__(self):
        self.active_benchmark: Optional[BenchmarkDetails] = None
        self._active_task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()

    def get_current_benchmark(self) -> Optional[BenchmarkDetails]:
        """Returns the currently active or most recently executed benchmark."""
        return self.active_benchmark

    async def start_benchmark(self, config: BenchmarkConfig) -> BenchmarkDetails:
        """
        Validates configuration and launches a benchmark experiment in the background.
        Raises RuntimeError if a benchmark is already running.
        """
        async with self._lock:
            if self.active_benchmark and self.active_benchmark.status in (
                BenchmarkLifecycleState.PREPARING,
                BenchmarkLifecycleState.RUNNING,
            ):
                raise RuntimeError("Another benchmark is currently running. Cancel or wait for it to finish.")

            benchmark_id = str(uuid.uuid4())[:8]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Estimate total execution time
            total_duration_sec = len(config.algorithms) * config.repetitions * config.duration

            self._cancel_event.clear()
            self.active_benchmark = BenchmarkDetails(
                id=benchmark_id,
                name=config.name,
                created_at=now_iso,
                status=BenchmarkLifecycleState.PREPARING,
                config=config,
                total_estimated_seconds=float(total_duration_sec),
                elapsed_seconds=0.0,
                progress_percent=0.0,
                is_simulated=False,
            )

            # Persist initial record
            benchmark_storage.save_benchmark(self.active_benchmark)

            # Launch background worker
            self._active_task = asyncio.create_task(self._run_lifecycle(self.active_benchmark))
            return self.active_benchmark

    async def cancel_benchmark(self, benchmark_id: str) -> bool:
        """Safely stops an active benchmark, triggers cleanup, and marks status CANCELLED."""
        async with self._lock:
            if not self.active_benchmark or self.active_benchmark.id != benchmark_id:
                return False

            if self.active_benchmark.status in (
                BenchmarkLifecycleState.COMPLETED,
                BenchmarkLifecycleState.FAILED,
                BenchmarkLifecycleState.CANCELLED,
            ):
                return True

            logger.info(f"Cancelling benchmark {benchmark_id}")
            self._cancel_event.set()
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()

            self.active_benchmark.status = BenchmarkLifecycleState.CANCELLED
            self.active_benchmark.error_message = "Benchmark cancelled by user"
            benchmark_storage.save_benchmark(self.active_benchmark)

            await self._broadcast_status({
                "type": "BENCHMARK_CANCELLED",
                "benchmark_id": benchmark_id,
                "message": "Benchmark was cancelled safely.",
            })

            # Cleanup faults & reset
            await self._cleanup_controller_state()
            return True

    async def _cleanup_controller_state(self, initial_algo: str = "round_robin"):
        """Restores original algorithm, health states, and resets connection tracking."""
        try:
            await controller_client.set_algorithm(initial_algo)
            for s in CONFIG.SERVERS:
                await controller_client.set_server_health(s.id, "HEALTHY", reason="Benchmark cleanup")
            await controller_client.reset_connection_tracking()
            logger.info("Restored baseline controller state after benchmark run.")
        except Exception as e:
            logger.warning(f"Error restoring controller state: {e}")

    async def _broadcast_status(self, payload: Dict):
        """Broadcasts progress updates to connected WebSocket clients."""
        try:
            await ws_manager.broadcast(payload)
        except Exception as e:
            logger.debug(f"WebSocket broadcast error: {e}")

    async def _run_lifecycle(self, benchmark: BenchmarkDetails):
        """Executes the full benchmark workflow across all selected algorithms and repetitions."""
        initial_status = await controller_client.get_status()
        initial_algo = initial_status.get("active_algorithm", "round_robin")

        try:
            # 1. Verification & Probe
            is_live_network, sample_srv = await WorkloadGenerator.probe_target(benchmark.config.target_url)
            benchmark.is_simulated = not is_live_network
            benchmark.status = BenchmarkLifecycleState.RUNNING

            logger.info(
                f"Starting Benchmark [{benchmark.id}] (Live Network: {is_live_network}, Target: {benchmark.config.target_url})"
            )

            await self._broadcast_status({
                "type": "BENCHMARK_STARTED",
                "benchmark_id": benchmark.id,
                "is_simulated": benchmark.is_simulated,
                "total_estimated_seconds": benchmark.total_estimated_seconds,
            })

            generator = WorkloadGenerator(benchmark.config, self._cancel_event)
            total_steps = len(benchmark.config.algorithms) * benchmark.config.repetitions
            current_step = 0

            # 2. Iterate across algorithms & repetitions
            for algo_name in benchmark.config.algorithms:
                if self._cancel_event.is_set():
                    break

                for rep in range(1, benchmark.config.repetitions + 1):
                    if self._cancel_event.is_set():
                        break

                    current_step += 1
                    benchmark.current_algorithm = algo_name
                    benchmark.current_repetition = rep

                    # Apply algorithm in controller and reset connection persistence
                    await controller_client.set_algorithm(algo_name)
                    await controller_client.reset_connection_tracking()
                    # Small settling pause for OpenFlow flow tables
                    await asyncio.sleep(0.4)

                    def on_progress(p_data: Dict):
                        benchmark.live_stats = BenchmarkLiveStats(
                            requests_sent=p_data.get("requests_sent", 0),
                            successful_requests=p_data.get("successful_requests", 0),
                            failed_requests=p_data.get("failed_requests", 0),
                            current_rps=p_data.get("current_rps", 0.0),
                            current_latency_ms=p_data.get("current_latency_ms", 0.0),
                            current_active_server=p_data.get("current_active_server"),
                        )
                        # Estimate overall progress percentage
                        step_progress = (current_step - 1) / max(1, total_steps)
                        intra_step = min(1.0, p_data.get("elapsed_seconds", 0) / max(1, benchmark.config.duration))
                        overall_pct = (step_progress + (intra_step / total_steps)) * 100.0
                        benchmark.progress_percent = round(min(99.0, overall_pct), 1)

                        asyncio.create_task(
                            self._broadcast_status({
                                "type": "BENCHMARK_PROGRESS",
                                "benchmark_id": benchmark.id,
                                "algorithm": algo_name,
                                "repetition": rep,
                                "progress_percent": benchmark.progress_percent,
                                "live_stats": benchmark.live_stats.model_dump(),
                            })
                        )

                    run_metric = await generator.run_workload(
                        algorithm_name=algo_name,
                        repetition=rep,
                        is_live_network=is_live_network,
                        progress_callback=on_progress,
                    )
                    benchmark.runs.append(run_metric)
                    benchmark_storage.save_benchmark(benchmark)

            if not self._cancel_event.is_set():
                # 3. Compute Aggregate Summaries
                eligible_count = len(CONFIG.SERVERS)
                summaries = []
                for algo in benchmark.config.algorithms:
                    algo_runs = [r for r in benchmark.runs if r.algorithm == algo]
                    if algo_runs:
                        summaries.append(aggregate_runs(algo_runs, eligible_count))

                benchmark.summary = summaries
                benchmark.status = BenchmarkLifecycleState.COMPLETED
                benchmark.progress_percent = 100.0
                benchmark.current_algorithm = None
                benchmark.current_repetition = None
                benchmark_storage.save_benchmark(benchmark)

                await self._broadcast_status({
                    "type": "BENCHMARK_COMPLETED",
                    "benchmark_id": benchmark.id,
                    "summary": [s.model_dump() for s in benchmark.summary],
                })

        except asyncio.CancelledError:
            benchmark.status = BenchmarkLifecycleState.CANCELLED
            benchmark_storage.save_benchmark(benchmark)
        except Exception as e:
            logger.exception(f"Benchmark {benchmark.id} failed: {e}")
            benchmark.status = BenchmarkLifecycleState.FAILED
            benchmark.error_message = str(e)
            benchmark_storage.save_benchmark(benchmark)
            await self._broadcast_status({
                "type": "BENCHMARK_FAILED",
                "benchmark_id": benchmark.id,
                "error": str(e),
            })
        finally:
            await self._cleanup_controller_state(initial_algo)


benchmark_engine = BenchmarkEngine()
