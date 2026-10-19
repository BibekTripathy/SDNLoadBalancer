"""
Scenarios S3 - S6 (and the S6Q queue check) for real Linux TCP in Mininet.

They are BUILT FROM the simulator's scenario definitions
(tcp_lab/simulator/scenarios.py), so both parts always use the same
bandwidth, delay, queue, loss, flows and timeline. This file only turns
one simulator "variant" into a Mininet "plan":

    forward   - tc conditions on sw1-eth1 (data direction, the bottleneck)
    reverse   - tc conditions on sw2-eth1 (ACK direction: same delay,
                no bandwidth limit, no loss, like the simulator's ACK path)
    flows     - which client sends to which server port, when, for how long
    udp       - background UDP sources
    timeline  - tc changes during the run (S5 bandwidth steps)

S1 and S2 (losing ONE CHOSEN segment) are simulator only: netem can drop
packets at random, but it cannot drop "segment number 300".

Delay: the simulator's delay_ms is one-way, so netem adds delay_ms in each
direction and the base RTT is 2 x delay_ms, the same as in the simulator.
"""

from tcp_lab.mininet import tc_controller
from tcp_lab.mininet.hosts import CLIENTS, SERVERS
from tcp_lab.simulator.scenarios import SCENARIOS

MININET_SCENARIOS = ["S3", "S4", "S5", "S6", "S6Q"]   # S6Q: the queue-vs-delay check

FIRST_TCP_PORT = 5201      # flow i uses iperf3 server port 5201 + i
FIRST_UDP_PORT = 5301      # UDP source j uses port 5301 + j


def forward_conditions(network):
    """Simulator network settings -> tc conditions for the bottleneck."""
    conditions = tc_controller.default_conditions()
    conditions["rate_mbps"] = network["bandwidth_mbps"]
    conditions["delay_ms"] = network["delay_ms"]
    conditions["loss_pct"] = network["loss_rate"] * 100.0    # 0.01 -> 1 %
    conditions["queue_packets"] = network["queue_size"]
    return conditions


def reverse_conditions(network):
    """ACK direction: only the propagation delay."""
    conditions = tc_controller.default_conditions()
    conditions["rate_mbps"] = None
    conditions["delay_ms"] = network["delay_ms"]
    return conditions


def build_timeline(forward, changes):
    """
    Simulator changes [(10.0, "bandwidth", 2.0), ...] -> tc timeline.
    Each step keeps the earlier changes, so (bandwidth, then loss) add up.
    """
    timeline = []
    current = forward
    for change in changes:
        change_time, what, value = change
        if what == "bandwidth":
            current = tc_controller.merged_conditions(current, {"rate_mbps": value})
        elif what == "loss_rate":
            current = tc_controller.merged_conditions(current, {"loss_pct": value * 100.0})
        else:
            raise ValueError("Unknown network change: " + what)
        timeline.append({"time": change_time, "conditions": current})
    return timeline


def assign_flows(sim_flows, duration):
    """
    Spread the TCP flows over the hosts: flow i goes from client i % 3 to
    server i % 2, on its own server port. Every flow runs until the end of
    the experiment, like the simulator's bulk flows.
    """
    clients = CLIENTS
    servers = SERVERS
    flows = []
    index = 0
    for sim_flow in sim_flows:
        client_name, client_ip = clients[index % len(clients)]
        server_name, server_ip = servers[index % len(servers)]
        flows.append({
            "flow": index,
            "client": client_name,
            "client_ip": client_ip,
            "server": server_name,
            "server_ip": server_ip,
            "port": FIRST_TCP_PORT + index,
            "start": sim_flow["start_time"],
            "duration": duration - sim_flow["start_time"],
        })
        index = index + 1
    return flows


def assign_udp(sim_udp):
    """All UDP background sources go from the last client to the last server."""
    client_name, client_ip = CLIENTS[-1]
    server_name, server_ip = SERVERS[-1]
    sources = []
    index = 0
    for udp in sim_udp:
        sources.append({
            "udp": index,
            "client": client_name,
            "client_ip": client_ip,
            "server": server_name,
            "server_ip": server_ip,
            "port": FIRST_UDP_PORT + index,
            "rate_mbps": udp["rate_mbps"],
            "start": udp["start"],
            "duration": udp["stop"] - udp["start"],
        })
        index = index + 1
    return sources


def build_plan(variant):
    """One simulator variant -> one Mininet plan (a plain dict)."""
    network = variant["network"]
    forward = forward_conditions(network)
    return {
        "label": variant["label"],
        "duration": network["duration"],
        "forward": forward,
        "reverse": reverse_conditions(network),
        "flows": assign_flows(variant["flows"], network["duration"]),
        "udp": assign_udp(variant["udp"]),
        "timeline": build_timeline(forward, variant["changes"]),
    }


def get_scenario(scenario_id):
    """Name, description and the list of plans of one scenario."""
    if scenario_id not in MININET_SCENARIOS:
        raise ValueError(scenario_id + " has no Mininet version; choose from "
                         + ", ".join(MININET_SCENARIOS))
    scenario = SCENARIOS[scenario_id]
    plans = []
    for variant in scenario["variants"]:
        plans.append(build_plan(variant))
    return {"id": scenario_id, "name": scenario["name"],
            "description": scenario["description"], "plans": plans}
