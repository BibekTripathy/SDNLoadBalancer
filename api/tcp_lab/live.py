"""
Live cwnd streaming over the dashboard WebSocket (/ws/events).

Two kinds of live run, one at a time (starting a new one stops the old):

  simulate  run the SIMULATOR for one scenario variant and the chosen
            algorithms, then play the cwnd of every flow back over time
  replay    play back a RECORDED Mininet run (the kernel's cwnd from ss)

Why "play back"? The simulator finishes a 20 s experiment in well under a
second, far too fast to watch. So it runs first (in a worker thread, so
the API stays responsive), and the samples are then sent in time order,
waiting between them: at speed 1, one simulated second takes one real
second; at speed 4 it takes a quarter. A recorded Mininet run is played
the same way. Nothing here is real-time Mininet traffic, and every
message says where its numbers come from ("source").

WebSocket messages (all have "type" and "run_id"):
  TCP_LAB_RUN_STARTED   what is being played, its duration, the source
  TCP_CWND_SAMPLE       time, algorithm, flow, cwnd, ssthresh, state
  TCP_LOSS_EVENT        a drop, fast retransmit or timeout (simulator only)
  TCP_LAB_RUN_FINISHED  end of the stream, with summary numbers (simulator)
  TCP_LAB_RUN_STOPPED   stopped early by the user or by a new run
"""

import asyncio
import logging
import time
import uuid

from api.tcp_lab import results
from api.websocket import ws_manager
from tcp_lab.analysis import metrics
from tcp_lab.simulator import ALGORITHMS
from tcp_lab.simulator.scenarios import SCENARIOS
from tcp_lab.simulator.tcp_sim import Simulator

logger = logging.getLogger(__name__)

SAMPLE_INTERVAL_S = 0.05      # one cwnd sample per flow per 50 ms of simulated time


# ---------------------------------------------------------------------------
# Running the simulator (plain, synchronous code)
# ---------------------------------------------------------------------------
def build_simulator(variant, seed):
    """Same as tcp_lab/run_sim_scenarios.py, without its plotting imports."""
    network = variant["network"]
    sim = Simulator(bandwidth_mbps=network["bandwidth_mbps"], delay_ms=network["delay_ms"],
                    queue_size=network["queue_size"], loss_rate=network["loss_rate"],
                    duration=network["duration"], seed=seed)
    for change_time, what, value in variant["changes"]:
        if what == "bandwidth":
            sim.change_bandwidth_at(change_time, value)
        else:
            sim.change_loss_rate_at(change_time, value)
    for udp in variant["udp"]:
        sim.add_udp_source(udp["rate_mbps"], udp["start"], udp["stop"])
    return sim


def simulate(variant, algorithm, seed):
    """Run one algorithm on one variant. Returns (summary, event rows)."""
    sim = build_simulator(variant, seed)
    for flow in variant["flows"]:
        sim.add_flow(algorithm, start_time=flow["start_time"],
                     total_segments=flow["total_segments"],
                     access_delay_ms=flow["access_delay_ms"],
                     initial_cwnd=flow["initial_cwnd"],
                     initial_ssthresh=flow["initial_ssthresh"],
                     rwnd=flow["rwnd"], scripted_drops=flow["scripted_drops"])
    summary = sim.run()
    return summary, sim.log_rows


def simulated_messages(variant, algorithms, seed, run_id):
    """
    Run every algorithm and turn the logs into the list of messages to send,
    sorted by simulated time. Also returns one summary row per algorithm.
    """
    messages = []
    summary_rows = []
    for algorithm in algorithms:
        summary, rows = simulate(variant, algorithm, seed)
        row = metrics.compute_run_metrics(summary, rows)
        summary_rows.append({"algorithm": algorithm, "source": "simulator", "seed": seed,
                             "goodput_mbps": row["goodput_mbps"],
                             "throughput_mbps": row["throughput_mbps"],
                             "retransmissions": row["retransmissions"],
                             "spurious_retransmissions": row["spurious_retransmissions"],
                             "timeouts": row["timeouts"],
                             "fast_retransmits": row["fast_retransmits"],
                             "avg_recovery_s": row["avg_recovery_s"],
                             "avg_rtt_ms": row["avg_rtt_ms"],
                             "jain_fairness": row["jain_fairness"]})
        for flow_id in range(len(variant["flows"])):
            for point in metrics.cwnd_series(rows, flow_id=flow_id, bin_s=SAMPLE_INTERVAL_S):
                messages.append({"type": "TCP_CWND_SAMPLE", "run_id": run_id,
                                 "source": "simulator", "algorithm": algorithm, "flow": flow_id,
                                 "time": point["time"], "cwnd": point["cwnd"],
                                 "ssthresh": point["ssthresh"], "state": point["state"]})
            for event in metrics.loss_events(rows, flow_id=flow_id):
                messages.append({"type": "TCP_LOSS_EVENT", "run_id": run_id,
                                 "source": "simulator", "algorithm": algorithm, "flow": flow_id,
                                 "time": event["time"], "event": event["event"],
                                 "seq": event["seq"], "cwnd": event["cwnd"]})
    messages.sort(key=lambda message: message["time"])
    return messages, summary_rows


def replay_messages(scenario_id, label, run_number, run_id):
    """Messages for a recorded Mininet run (cwnd from ss, already in time order)."""
    messages = []
    for sample in results.mininet_cwnd_samples(scenario_id, label, run_number):
        messages.append({"type": "TCP_CWND_SAMPLE", "run_id": run_id, "source": "mininet",
                         "algorithm": "linux_reno", "flow": sample["flow"],
                         "time": sample["time"], "cwnd": sample["cwnd"],
                         "ssthresh": sample["ssthresh"],
                         "state": None})      # ss does not report slow start / avoidance
    return messages


# ---------------------------------------------------------------------------
# One live run at a time
# ---------------------------------------------------------------------------
class LiveRunner:
    def __init__(self):
        self.task = None
        self.status = {"state": "idle"}

    def get_status(self):
        return self.status

    async def stop(self, reason="stopped by user"):
        """Cancel the running stream (if any) and tell the clients."""
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            run_id = self.status.get("run_id")
            self.status = dict(self.status)
            self.status["state"] = "stopped"
            await ws_manager.broadcast({"type": "TCP_LAB_RUN_STOPPED", "run_id": run_id,
                                        "reason": reason})
            return True
        return False

    async def start_simulation(self, scenario_id, label, algorithms, seed, speed):
        variant = results.check_variant(scenario_id, label)
        for algorithm in algorithms:
            if algorithm not in ALGORITHMS:
                raise ValueError("Unknown algorithm '" + algorithm + "'")
        await self.stop(reason="a new run was started")
        run_id = uuid.uuid4().hex[:8]
        # The simulator is CPU work: run it in a thread so the API keeps answering
        messages, summary_rows = await asyncio.to_thread(
            simulated_messages, variant, algorithms, seed, run_id)
        info = {"run_id": run_id, "mode": "simulate", "source": "simulator",
                "scenario": scenario_id, "scenario_name": SCENARIOS[scenario_id]["name"],
                "variant": label, "algorithms": algorithms, "seed": seed, "speed": speed,
                "duration": variant["network"]["duration"],
                "num_flows": len(variant["flows"]), "messages": len(messages)}
        return self.begin(info, messages, summary_rows)

    async def start_replay(self, scenario_id, label, run_number, speed):
        variant = results.check_variant(scenario_id, label)
        await self.stop(reason="a new run was started")
        run_id = uuid.uuid4().hex[:8]
        messages = await asyncio.to_thread(replay_messages, scenario_id, label, run_number, run_id)
        info = {"run_id": run_id, "mode": "replay", "source": "mininet",
                "scenario": scenario_id, "scenario_name": SCENARIOS[scenario_id]["name"],
                "variant": label, "algorithms": ["linux_reno"], "mininet_run": run_number,
                "speed": speed, "duration": variant["network"]["duration"],
                "num_flows": len(variant["flows"]), "messages": len(messages)}
        return self.begin(info, messages, None)

    def begin(self, info, messages, summary_rows):
        self.status = dict(info)
        self.status["state"] = "running"
        self.status["progress_s"] = 0.0
        self.task = asyncio.create_task(self.play(info, messages, summary_rows))
        return self.status

    async def play(self, info, messages, summary_rows):
        """Send the messages, waiting so that simulated time runs at `speed`."""
        await ws_manager.broadcast(dict(info, type="TCP_LAB_RUN_STARTED"))
        started = time.monotonic()
        for message in messages:
            due = started + message["time"] / info["speed"]
            wait = due - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await ws_manager.broadcast(message)
            self.status["progress_s"] = message["time"]
        self.status["state"] = "finished"
        await ws_manager.broadcast({"type": "TCP_LAB_RUN_FINISHED", "run_id": info["run_id"],
                                    "source": info["source"], "results": summary_rows})


live_runner = LiveRunner()
