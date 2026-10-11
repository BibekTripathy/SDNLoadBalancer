"""
Asynchronous HTTP Load Generator and Workload Simulator for the SDN Benchmarking Laboratory.
Features token-bucket pacing, high-resolution latency timing, real HTTP backend identification,
and an algorithm-accurate fallback simulation mode when Mininet VIP is unreachable.
"""

import asyncio
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx

from api.benchmark.metrics import (
    calculate_error_rate_pct,
    calculate_jains_fairness_index,
    calculate_percentile,
    calculate_throughput_mbps,
)
from api.benchmark.models import BenchmarkConfig, RunMetrics
from controller.algorithms import get_algorithm
from controller.config import CONFIG, BackendServer

logger = logging.getLogger(__name__)


class WorkloadGenerator:
    """Orchestrates reproducible HTTP benchmarking workloads."""

    def __init__(self, config: BenchmarkConfig, cancel_event: asyncio.Event):
        self.config = config
        self.cancel_event = cancel_event

    @staticmethod
    async def probe_target(target_url: str, timeout: float = 1.0) -> Tuple[bool, Optional[str]]:
        """
        Tests whether the target Virtual IP HTTP endpoint is reachable.
        Returns (is_reachable, sample_server_id).
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(target_url)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return True, data.get("server_id")
                    except Exception:
                        return True, None
                return False, None
        except Exception:
            return False, None

    async def run_workload(
        self,
        algorithm_name: str,
        repetition: int,
        is_live_network: bool,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> RunMetrics:
        """
        Executes a benchmark workload for the given algorithm and repetition.
        """
        if is_live_network:
            return await self._run_live_http_workload(algorithm_name, repetition, progress_callback)
        else:
            return await self._run_simulated_workload(algorithm_name, repetition, progress_callback)

    async def _run_live_http_workload(
        self,
        algorithm_name: str,
        repetition: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> RunMetrics:
        """
        Generates real HTTP traffic against http://10.0.0.100:80/ through Open vSwitch.
        Measures real request latencies, status codes, and server IDs returned by server_app.py.
        """
        rate = self.config.rate
        concurrency = self.config.concurrency
        duration = self.config.duration
        warmup = self.config.warmup_duration
        target_url = self.config.target_url

        steady_latencies: List[float] = []
        steady_bytes = 0
        steady_status_codes: Dict[str, int] = {}
        steady_backend_dist: Dict[str, int] = {}
        steady_successful = 0
        steady_failed = 0
        steady_timeouts = 0

        total_sent = 0
        live_successful = 0
        live_failed = 0
        time_series: List[Dict[str, Any]] = []

        start_time = time.perf_counter()
        next_request_time = start_time
        interval = 1.0 / max(1, rate)

        semaphore = asyncio.Semaphore(concurrency)
        last_progress_tick = start_time
        active_server_id: Optional[str] = None

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=5.0),
            limits=httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency),
        ) as client:

            async def send_single_request(req_idx: int):
                nonlocal total_sent, live_successful, live_failed, active_server_id
                nonlocal steady_successful, steady_failed, steady_timeouts, steady_bytes

                async with semaphore:
                    if self.cancel_event.is_set():
                        return

                    t0 = time.perf_counter()
                    is_warmup = (t0 - start_time) < warmup
                    status_code = 0
                    server_id = "unknown"
                    bytes_received = 0
                    success = False

                    try:
                        resp = await client.get(target_url)
                        status_code = resp.status_code
                        bytes_received = len(resp.content)
                        if resp.status_code == 200:
                            success = True
                            try:
                                data = resp.json()
                                server_id = data.get("server_id", "unknown")
                            except Exception:
                                server_id = "server_unparsed"
                    except httpx.TimeoutException:
                        status_code = 408
                    except Exception:
                        status_code = 502

                    t1 = time.perf_counter()
                    latency_ms = max(0.1, (t1 - t0) * 1000.0)

                    total_sent += 1
                    if success:
                        live_successful += 1
                        active_server_id = server_id
                    else:
                        live_failed += 1

                    if not is_warmup:
                        steady_latencies.append(latency_ms)
                        steady_bytes += bytes_received
                        code_str = str(status_code)
                        steady_status_codes[code_str] = steady_status_codes.get(code_str, 0) + 1

                        if success:
                            steady_successful += 1
                            steady_backend_dist[server_id] = steady_backend_dist.get(server_id, 0) + 1
                        else:
                            steady_failed += 1
                            if status_code == 408:
                                steady_timeouts += 1

            # Dispatch loop with token-bucket pacing
            tasks = []
            while not self.cancel_event.is_set():
                now = time.perf_counter()
                elapsed = now - start_time
                if elapsed >= duration:
                    break

                # Progress reporting every ~0.5 seconds
                if now - last_progress_tick >= 0.5:
                    last_progress_tick = now
                    current_rps = live_successful / max(0.1, elapsed)
                    recent_lat = (
                        sum(steady_latencies[-10:]) / len(steady_latencies[-10:])
                        if steady_latencies
                        else 0.0
                    )
                    time_series.append({
                        "elapsed": round(elapsed, 1),
                        "rps": round(current_rps, 1),
                        "latency_ms": round(recent_lat, 2),
                    })
                    if progress_callback:
                        progress_callback({
                            "requests_sent": total_sent,
                            "successful_requests": live_successful,
                            "failed_requests": live_failed,
                            "current_rps": round(current_rps, 1),
                            "current_latency_ms": round(recent_lat, 2),
                            "current_active_server": active_server_id,
                            "elapsed_seconds": round(elapsed, 1),
                        })

                # Fire request if scheduled
                if now >= next_request_time:
                    tasks.append(asyncio.create_task(send_single_request(len(tasks))))
                    next_request_time += interval
                else:
                    sleep_time = min(0.01, max(0.001, next_request_time - now))
                    await asyncio.sleep(sleep_time)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        steady_duration = max(0.001, duration - warmup)
        total_steady = steady_successful + steady_failed
        achieved_rps = round(total_steady / steady_duration, 2)
        err_rate = calculate_error_rate_pct(steady_failed, total_steady)
        mbps = calculate_throughput_mbps(steady_bytes, steady_duration)

        mean_lat = (sum(steady_latencies) / len(steady_latencies)) if steady_latencies else 0.0
        p50 = calculate_percentile(steady_latencies, 50.0)
        p95 = calculate_percentile(steady_latencies, 95.0)
        p99 = calculate_percentile(steady_latencies, 99.0)

        eligible_count = len(CONFIG.SERVERS)
        jain = calculate_jains_fairness_index(steady_backend_dist, eligible_count)

        dist_pct = {
            sid: round((cnt / max(1, steady_successful)) * 100.0, 1)
            for sid, cnt in steady_backend_dist.items()
        }

        return RunMetrics(
            algorithm=algorithm_name,
            repetition=repetition,
            total_requests=total_steady,
            successful_requests=steady_successful,
            failed_requests=steady_failed,
            error_rate_pct=err_rate,
            achieved_rps=achieved_rps,
            throughput_mbps=mbps,
            mean_latency_ms=round(mean_lat, 2),
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            status_codes=steady_status_codes,
            timeouts=steady_timeouts,
            backend_distribution=steady_backend_dist,
            backend_distribution_pct=dist_pct,
            jains_fairness_index=jain,
            recovery_time_sec=None,
            is_simulated=False,
            time_series=time_series,
        )

    async def _run_simulated_workload(
        self,
        algorithm_name: str,
        repetition: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> RunMetrics:
        """
        Simulated benchmark workload when Mininet VIP is unreachable.
        Executes the ACTUAL algorithm from controller/algorithms to determine backend selection,
        faithfully calculating Jain's Fairness Index, latency distribution, and throughput.
        Clearly marked as is_simulated = True.
        """
        algo_instance = get_algorithm(algorithm_name)
        rate = self.config.rate
        duration = self.config.duration
        warmup = self.config.warmup_duration
        servers = list(CONFIG.SERVERS)

        # Base server characteristics
        base_latencies = {"server1": 1.4, "server2": 1.9, "server3": 2.5}
        if self.config.inject_latency_ms:
            for s_id, added in self.config.inject_latency_ms.items():
                if s_id in base_latencies:
                    base_latencies[s_id] += added

        simulated_connections = {s.id: 0 for s in servers}
        simulated_bw = {s.id: 0.1 for s in servers}
        steady_latencies: List[float] = []
        steady_backend_dist: Dict[str, int] = {s.id: 0 for s in servers}
        steady_status_codes: Dict[str, int] = {"200": 0}
        steady_successful = 0
        steady_failed = 0
        steady_bytes = 0

        time_series: List[Dict[str, Any]] = []
        start_time = time.perf_counter()
        next_tick = start_time
        interval = 1.0 / max(1, rate)
        last_progress_tick = start_time
        active_server_id = None
        total_sent = 0
        recovery_time_sec: Optional[float] = None
        failure_active = False

        while not self.cancel_event.is_set():
            now = time.perf_counter()
            elapsed = now - start_time
            if elapsed >= duration:
                break

            # Handle failure scenario injection if specified
            active_servers = list(servers)
            if self.config.failure_scenario:
                scen = self.config.failure_scenario
                if elapsed >= scen.at_second:
                    if scen.recover_at_second is None or elapsed < scen.recover_at_second:
                        active_servers = [s for s in servers if s.id != scen.server_id]
                        failure_active = True
                    elif failure_active and scen.recover_at_second and elapsed >= scen.recover_at_second:
                        failure_active = False
                        recovery_time_sec = round(scen.recover_at_second - scen.at_second, 2)

            # Periodic progress update
            if now - last_progress_tick >= 0.5:
                last_progress_tick = now
                curr_rps = total_sent / max(0.1, elapsed)
                recent_lat = (
                    sum(steady_latencies[-10:]) / len(steady_latencies[-10:])
                    if steady_latencies
                    else 1.8
                )
                time_series.append({
                    "elapsed": round(elapsed, 1),
                    "rps": round(curr_rps, 1),
                    "latency_ms": round(recent_lat, 2),
                })
                if progress_callback:
                    progress_callback({
                        "requests_sent": total_sent,
                        "successful_requests": steady_successful,
                        "failed_requests": steady_failed,
                        "current_rps": round(curr_rps, 1),
                        "current_latency_ms": round(recent_lat, 2),
                        "current_active_server": active_server_id,
                        "elapsed_seconds": round(elapsed, 1),
                    })

            if now >= next_tick:
                next_tick += interval
                total_sent += 1
                is_warmup = elapsed < warmup

                # Prepare mock telemetry snapshot for algorithm decision
                telemetry_snapshot = {
                    s.id: {
                        "active_connections": simulated_connections[s.id],
                        "bandwidth_mbps": simulated_bw[s.id],
                        "latency_ms": base_latencies.get(s.id, 1.5),
                        "packet_loss_ratio": 0.0,
                    }
                    for s in servers
                }

                client_info = {
                    "client_ip": "10.0.0.1",
                    "client_port": 10000 + (total_sent % 50000),
                    "protocol": "TCP",
                }

                try:
                    if not active_servers:
                        raise RuntimeError("All servers down")
                    selected, _ = algo_instance.select_server(
                        servers=active_servers,
                        client_info=client_info,
                        telemetry_data=telemetry_snapshot,
                    )
                    active_server_id = selected.id
                    # Update simulated load
                    simulated_connections[selected.id] += 1
                    simulated_bw[selected.id] += 0.05
                    # Natural decay
                    if total_sent % 5 == 0:
                        for sid in simulated_connections:
                            simulated_connections[sid] = max(0, simulated_connections[sid] - 1)

                    base_lat = base_latencies.get(selected.id, 1.8)
                    lat = max(0.5, base_lat + random.gauss(0, 0.3) + (simulated_connections[selected.id] * 0.1))
                    lat = round(lat, 2)
                    req_bytes = 180 + random.randint(0, 40)

                    if not is_warmup:
                        steady_successful += 1
                        steady_latencies.append(lat)
                        steady_bytes += req_bytes
                        steady_backend_dist[selected.id] = steady_backend_dist.get(selected.id, 0) + 1
                        steady_status_codes["200"] = steady_status_codes.get("200", 0) + 1
                except Exception:
                    if not is_warmup:
                        steady_failed += 1
                        steady_status_codes["503"] = steady_status_codes.get("503", 0) + 1

            else:
                await asyncio.sleep(min(0.01, max(0.001, next_tick - now)))

        steady_duration = max(0.001, duration - warmup)
        total_steady = steady_successful + steady_failed
        achieved_rps = round(total_steady / steady_duration, 2)
        err_rate = calculate_error_rate_pct(steady_failed, total_steady)
        mbps = calculate_throughput_mbps(steady_bytes, steady_duration)

        mean_lat = (sum(steady_latencies) / len(steady_latencies)) if steady_latencies else 0.0
        p50 = calculate_percentile(steady_latencies, 50.0)
        p95 = calculate_percentile(steady_latencies, 95.0)
        p99 = calculate_percentile(steady_latencies, 99.0)

        eligible_count = len(CONFIG.SERVERS)
        jain = calculate_jains_fairness_index(steady_backend_dist, eligible_count)

        dist_pct = {
            sid: round((cnt / max(1, steady_successful)) * 100.0, 1)
            for sid, cnt in steady_backend_dist.items()
        }

        return RunMetrics(
            algorithm=algorithm_name,
            repetition=repetition,
            total_requests=total_steady,
            successful_requests=steady_successful,
            failed_requests=steady_failed,
            error_rate_pct=err_rate,
            achieved_rps=achieved_rps,
            throughput_mbps=mbps,
            mean_latency_ms=round(mean_lat, 2),
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            status_codes=steady_status_codes,
            timeouts=0,
            backend_distribution=steady_backend_dist,
            backend_distribution_pct=dist_pct,
            jains_fairness_index=jain,
            recovery_time_sec=recovery_time_sec,
            is_simulated=True,
            time_series=time_series,
        )
