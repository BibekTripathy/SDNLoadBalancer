"""
Experiment scenarios S1 - S6 for the simulator.

Each scenario is a plain dict with a list of "variants". A variant says:
  network    - bottleneck settings passed to Simulator(...)
  flows      - list of TCP flows; every flow runs the algorithm under test
  udp        - list of UDP background sources (rate_mbps, start, stop)
  changes    - list of (time, "bandwidth" or "loss_rate", value) changes mid-run

Defaults used unless a variant overrides them:
  10 Mbps bottleneck, 20 ms one-way delay (base RTT 40 ms),
  queue of 100 packets, initial ssthresh 32 segments, 1460 byte MSS.

S6Q is an extra check for S6 (queue size vs delay), not one of S1 - S6.

For S1 and S2 the queue is large so that the ONLY losses are the scripted
ones: this isolates loss recovery from congestion. Dropped segments are
chosen around seq 300, when the sender is already in congestion avoidance.
"""

DEFAULT_NETWORK = {
    "bandwidth_mbps": 10.0,
    "delay_ms": 20.0,
    "queue_size": 100,
    "loss_rate": 0.0,
    "duration": 20.0,
    "seed": 1,
}

DEFAULT_FLOW = {
    "start_time": 0.0,
    "total_segments": None,     # bulk transfer, runs until the end
    "access_delay_ms": 0.0,
    "initial_cwnd": 1,
    "initial_ssthresh": 32,
    "rwnd": 1000,
    "scripted_drops": [],
}


def network(**overrides):
    """DEFAULT_NETWORK with some values replaced."""
    result = dict(DEFAULT_NETWORK)
    for key in overrides:
        result[key] = overrides[key]
    return result


def flow(**overrides):
    """DEFAULT_FLOW with some values replaced."""
    result = dict(DEFAULT_FLOW)
    for key in overrides:
        result[key] = overrides[key]
    return result


def scripted_drop_variant(label, drops):
    return {
        "label": label,
        "network": network(queue_size=1000, duration=4.0),
        "flows": [flow(scripted_drops=drops)],
        "udp": [],
        "changes": [],
    }


SCENARIOS = {
    "S1": {
        "name": "Single packet loss",
        "description": "One segment (seq 300) is dropped once. Shows fast retransmit "
                       "and fast recovery in their simplest form.",
        "variants": [
            scripted_drop_variant("1_loss", [300]),
        ],
    },
    "S2": {
        "name": "Multiple losses in one window",
        "description": "2, 3 or 4 segments from the SAME window are dropped. "
                       "Key comparison: Reno usually times out, New Reno repairs "
                       "one hole per RTT, Tahoe slow-starts and resends.",
        "variants": [
            scripted_drop_variant("2_losses", [300, 303]),
            scripted_drop_variant("3_losses", [300, 303, 306]),
            scripted_drop_variant("4_losses", [300, 303, 306, 309]),
        ],
    },
    "S3": {
        "name": "Random packet loss",
        "description": "Random (Bernoulli) loss on the bottleneck: 0.1 %, 1 %, 5 %.",
        "variants": [
            {"label": "loss_0.1pct", "network": network(loss_rate=0.001),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "loss_1pct", "network": network(loss_rate=0.01),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "loss_5pct", "network": network(loss_rate=0.05),
             "flows": [flow()], "udp": [], "changes": []},
        ],
    },
    "S4": {
        "name": "Increasing traffic load",
        "description": "More parallel TCP flows (1, 2, 4) and finally 4 flows plus "
                       "UDP background traffic ramping up 2 -> 4 -> 6 Mbps.",
        "variants": [
            {"label": "1_flow", "network": network(),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "2_flows", "network": network(),
             "flows": [flow(), flow(start_time=2.0)], "udp": [], "changes": []},
            {"label": "4_flows", "network": network(),
             "flows": [flow(), flow(start_time=2.0), flow(start_time=4.0),
                       flow(start_time=6.0)],
             "udp": [], "changes": []},
            {"label": "4_flows_udp_ramp", "network": network(),
             "flows": [flow(), flow(start_time=2.0), flow(start_time=4.0),
                       flow(start_time=6.0)],
             # three 2 Mbps sources switching on one after another = a ramp
             "udp": [{"rate_mbps": 2.0, "start": 8.0, "stop": 20.0},
                     {"rate_mbps": 2.0, "start": 12.0, "stop": 20.0},
                     {"rate_mbps": 2.0, "start": 16.0, "stop": 20.0}],
             "changes": []},
        ],
    },
    "S5": {
        "name": "Variable bandwidth",
        "description": "Bottleneck steps 10 Mbps -> 2 Mbps at t=10 s -> 10 Mbps at t=20 s.",
        "variants": [
            {"label": "step_down_up", "network": network(duration=30.0, queue_size=50),
             "flows": [flow()], "udp": [],
             "changes": [(10.0, "bandwidth", 2.0), (20.0, "bandwidth", 10.0)]},
        ],
    },
    "S6": {
        "name": "Different delays",
        "description": "Base RTT of 10 ms, 50 ms and 200 ms (one-way delay = RTT / 2). "
                       "Higher RTT means slower window growth and slower recovery. "
                       "0.5 % random loss so that recovery happens in every run.",
        "variants": [
            {"label": "rtt_10ms", "network": network(delay_ms=5.0, loss_rate=0.005),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "rtt_50ms", "network": network(delay_ms=25.0, loss_rate=0.005),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "rtt_200ms", "network": network(delay_ms=100.0, loss_rate=0.005),
             "flows": [flow()], "udp": [], "changes": []},
        ],
    },
    # Not one of the assignment's six: a check for S6. Is the drop in goodput
    # between 10 ms and 50 ms RTT caused by the queue or by loss x RTT?
    # Same as S6 rtt_50ms, but the queue size changes (25 / 100 / 400) and
    # one variant has no random loss at all.
    "S6Q": {
        "name": "Queue or delay? (S6 check)",
        "description": "S6 rtt_50ms (0.5 % loss) with queues of 25, 100 and 400 "
                       "packets, and once without random loss. If the queue mattered, "
                       "goodput would change with the queue size.",
        "variants": [
            {"label": "rtt_50ms_queue_25",
             "network": network(delay_ms=25.0, loss_rate=0.005, queue_size=25),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "rtt_50ms_queue_100",
             "network": network(delay_ms=25.0, loss_rate=0.005, queue_size=100),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "rtt_50ms_queue_400",
             "network": network(delay_ms=25.0, loss_rate=0.005, queue_size=400),
             "flows": [flow()], "udp": [], "changes": []},
            {"label": "rtt_50ms_no_loss",
             "network": network(delay_ms=25.0, loss_rate=0.0, queue_size=100),
             "flows": [flow()], "udp": [], "changes": []},
        ],
    },
}


def has_random_loss(variant):
    """
    True if the variant uses random loss anywhere. Only then does the seed
    change the result; every other variant gives the same numbers each time.
    """
    if variant["network"]["loss_rate"] > 0:
        return True
    for change in variant["changes"]:
        if change[1] == "loss_rate" and change[2] > 0:
            return True
    return False


def list_scenarios():
    """Short description of every scenario (used by the API later)."""
    result = []
    for scenario_id in SCENARIOS:
        scenario = SCENARIOS[scenario_id]
        labels = []
        for variant in scenario["variants"]:
            labels.append(variant["label"])
        result.append({
            "id": scenario_id,
            "name": scenario["name"],
            "description": scenario["description"],
            "variants": labels,
        })
    return result
