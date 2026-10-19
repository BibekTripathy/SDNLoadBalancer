"""
Tests for the Mininet scenario runner (Phase 4) that need no root and no
Mininet: the scenario plans, the cleanup commands, and how one run's raw
measurements become a result row.
"""

import os

import pytest

from tcp_lab import run_mininet_scenarios as runner
from tcp_lab.mininet import cleanup, scenarios, tc_controller
from tcp_lab.simulator.scenarios import SCENARIOS

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "tcp_lab")


# ---------------------------------------------------------------------------
# Scenario plans: same numbers as the simulator
# ---------------------------------------------------------------------------
def test_only_s3_to_s6_have_a_mininet_version():
    assert scenarios.MININET_SCENARIOS == ["S3", "S4", "S5", "S6", "S6Q"]
    with pytest.raises(ValueError):
        scenarios.get_scenario("S1")


def test_plans_use_the_simulator_settings():
    for scenario_id in scenarios.MININET_SCENARIOS:
        plans = scenarios.get_scenario(scenario_id)["plans"]
        variants = SCENARIOS[scenario_id]["variants"]
        assert len(plans) == len(variants)
        for plan, variant in zip(plans, variants):
            network = variant["network"]
            assert plan["label"] == variant["label"]
            assert plan["duration"] == network["duration"]
            assert plan["forward"]["rate_mbps"] == network["bandwidth_mbps"]
            assert plan["forward"]["delay_ms"] == network["delay_ms"]
            assert plan["forward"]["queue_packets"] == network["queue_size"]
            assert plan["forward"]["loss_pct"] == pytest.approx(network["loss_rate"] * 100)
            # ACK direction: same delay, no shaping, no loss
            assert plan["reverse"]["delay_ms"] == network["delay_ms"]
            assert plan["reverse"]["rate_mbps"] is None
            assert plan["reverse"]["loss_pct"] == 0
            assert len(plan["flows"]) == len(variant["flows"])


def test_s4_flows_spread_over_hosts_with_own_ports():
    plans = scenarios.get_scenario("S4")["plans"]
    four = plans[3]
    assert four["label"] == "4_flows_udp_ramp"
    clients = [flow["client"] for flow in four["flows"]]
    servers = [flow["server"] for flow in four["flows"]]
    ports = [flow["port"] for flow in four["flows"]]
    assert clients == ["c1", "c2", "c3", "c1"]
    assert servers == ["sv1", "sv2", "sv1", "sv2"]
    assert ports == [5201, 5202, 5203, 5204]
    # every flow runs until the end, like the simulator's bulk flows
    assert [flow["start"] + flow["duration"] for flow in four["flows"]] == [20.0] * 4
    udp_ports = [source["port"] for source in four["udp"]]
    assert udp_ports == [5301, 5302, 5303]
    assert [source["duration"] for source in four["udp"]] == [12.0, 8.0, 4.0]


def test_s5_timeline_steps_down_and_up():
    plan = scenarios.get_scenario("S5")["plans"][0]
    times = [step["time"] for step in plan["timeline"]]
    rates = [step["conditions"]["rate_mbps"] for step in plan["timeline"]]
    assert times == [10.0, 20.0]
    assert rates == [2.0, 10.0]
    # the queue setting is kept in every step
    assert plan["timeline"][0]["conditions"]["queue_packets"] == 50


def test_timeline_changes_add_up():
    forward = tc_controller.default_conditions()
    timeline = scenarios.build_timeline(forward, [(5.0, "bandwidth", 2.0), (8.0, "loss_rate", 0.01)])
    assert timeline[1]["conditions"]["rate_mbps"] == 2.0     # kept from the first change
    assert timeline[1]["conditions"]["loss_pct"] == pytest.approx(1.0)
    assert forward["rate_mbps"] == 10.0                       # the original is not changed


def test_schedule_is_in_start_order():
    plan = scenarios.get_scenario("S4")["plans"][3]
    starts = [entry["item"]["start"] for entry in runner.build_schedule(plan)]
    assert starts == [0.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0]
    clients, servers = runner.hosts_in_plan(plan)
    assert clients == ["c1", "c2", "c3"]
    assert servers == ["sv1", "sv2"]


# ---------------------------------------------------------------------------
# Cleanup (grep -E, only the lab's own names)
# ---------------------------------------------------------------------------
def test_cleanup_commands_use_grep_e_and_lab_names_only():
    switches, hosts = cleanup.names_for("dumbbell")
    command = cleanup.build_list_links_command(switches, hosts)
    assert "grep -E" in command
    assert "egrep" not in command
    assert "(sw1|sw2|c1|c2|c3|sv1|sv2)-eth" in command
    commands = cleanup.build_cleanup_commands(switches, hosts, ["sw1-eth1"])
    assert commands[0] == "ovs-vsctl --if-exists del-br sw1"
    assert "ip link del sw1-eth1 2> /dev/null" in commands
    assert "pkill -9 -f 'mininet:c1$'" in commands
    for command in commands:
        assert "ryu" not in command      # never touches the controller


# ---------------------------------------------------------------------------
# From raw measurements to a result row
# ---------------------------------------------------------------------------
def test_bottleneck_drops_split_queue_and_random():
    with open(os.path.join(DATA_DIR, "tc_stats_sample.txt")) as handle:
        stats = tc_controller.parse_tc_stats(handle.read())
    drops = runner.bottleneck_drops(stats)
    # canned run: 2 % netem loss, tbf never overflowed
    assert drops == {"queue_drops": 0, "random_drops": 52, "packets_offered": 2749}


def test_bottleneck_drops_queue_only():
    # numbers from the real smoke test: root netem repeats its tbf child's drops
    stats = [{"kind": "netem", "sent_packets": 9298, "dropped": 130},
             {"kind": "tbf", "sent_packets": 9298, "dropped": 130}]
    drops = runner.bottleneck_drops(stats)
    assert drops["queue_drops"] == 130
    assert drops["random_drops"] == 0


def fake_flow(goodput, received_bytes, retransmits, pcap_retx, arrived_bytes, spurious, rtts):
    return {
        "iperf3": {"goodput_mbps": goodput, "received_bytes": received_bytes,
                   "retransmits": retransmits},
        "pcap_sender": {"retransmissions": pcap_retx},
        "pcap_receiver": {"data_bytes": arrived_bytes},
        "spurious": {"spurious_retransmissions": spurious},
        "ss": {"rtt_ms": rtts, "initial_cwnd": 1},
    }


def fake_counters(retrans, timeouts):
    return {"TcpRetransSegs": retrans, "TcpExtTCPTimeouts": timeouts,
            "TcpExtTCPFastRetrans": retrans - timeouts, "TcpExtTCPRenoRecovery": 3,
            "TcpExtTCPRenoRecoveryFail": 1}


def test_result_row_adds_up_flows_and_labels_the_source():
    plan = {"duration": 20.0}
    raw = {"seed": 2,
           "nstat": {"c1": fake_counters(30, 2), "c2": fake_counters(20, 1)},
           "tc_stats": [{"kind": "netem", "sent_packets": 1950, "dropped": 50},
                        {"kind": "tbf", "sent_packets": 1950, "dropped": 40}]}
    flows = [fake_flow(6.0, 15_000_000, 30, 30, 15_500_000, 5, [40.0, 50.0]),
             fake_flow(2.0, 5_000_000, 20, 20, 5_250_000, 0, [60.0])]
    udp = [{"iperf3": {"received_mbps": 1.98771}}, {"iperf3": None}]
    row = runner.build_result_row(plan, raw, flows, udp, run_number=2)

    assert row["source"] == "mininet"
    assert row["algorithm"] == "linux_reno"
    assert row["run"] == 2
    assert row["netem_seed"] == 2
    # goodput = 20 MB read by the servers in 20 s = 8 Mbit/s
    assert row["goodput_mbps"] == 8.0
    # throughput = 20.75 MB arrived (resends included) in 20 s
    assert row["throughput_mbps"] == 8.3
    assert row["retransmissions"] == 50
    assert row["retransmissions_by_source"] == {"iperf3": 50, "nstat": 50, "pcap": 50}
    assert row["spurious_retransmissions"] == 5
    assert row["needed_retransmissions"] == 45
    assert row["timeouts"] == 3
    assert row["queue_drops"] == 40
    assert row["random_drops"] == 10
    assert row["packet_loss_rate"] == 0.025          # 50 dropped / 2000 offered
    assert row["avg_rtt_ms"] == 50.0
    assert row["per_flow_goodput_mbps"] == [6.0, 2.0]
    assert row["jain_fairness"] == 0.8               # (6+2)^2 / (2 * (36+4))
    assert row["udp_received_mbps"] == [1.9877, None]
    assert row["initial_cwnd"] == [1, 1]


def checked_flow(number, initial_cwnd):
    return {"flow": number, "client": "c1", "server": "sv1",
            "ss": {"initial_cwnd": initial_cwnd,
                   "first_established": {"time": 1.1, "cwnd": 10, "delivered": 1}}}


def test_initial_cwnd_check():
    failures, unknown = runner.check_initial_cwnd([checked_flow(0, 1), checked_flow(1, 1)])
    assert failures == [] and unknown == []

    failures, unknown = runner.check_initial_cwnd([checked_flow(0, 10), checked_flow(1, None)])
    assert len(failures) == 1
    assert failures[0].startswith("flow0 (c1 -> sv1): initial cwnd estimated as 10, expected 1")
    assert unknown == ["flow1 (c1 -> sv1): initial cwnd could not be worked out from ss"]


def test_missing_iperf3_report_gives_none_not_a_wrong_total():
    plan = {"duration": 20.0}
    raw = {"seed": 1, "nstat": {"c1": fake_counters(10, 0)}, "tc_stats": []}
    broken = fake_flow(0, 0, 0, 7, 100, 0, [])
    broken["iperf3"] = None
    row = runner.build_result_row(plan, raw, [broken], [], run_number=1)
    assert row["goodput_mbps"] is None
    assert row["retransmissions"] is None
    assert row["needed_retransmissions"] is None
    assert row["retransmissions_by_source"]["pcap"] == 7
    assert row["packet_loss_rate"] is None


def test_store_variant_replaces_same_label():
    summary = {"variants": [{"label": "a", "runs": 3}, {"label": "b", "runs": 3}]}
    runner.store_variant(summary, {"label": "b", "runs": 5})
    runner.store_variant(summary, {"label": "c", "runs": 1})
    assert [(item["label"], item["runs"]) for item in summary["variants"]] == [
        ("a", 3), ("b", 5), ("c", 1)]
