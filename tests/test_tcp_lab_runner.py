"""
Tests for the TCP Lab scenario runner, metrics and plots (simulator part).
"""

import json
import os

from tcp_lab.analysis import metrics
from tcp_lab.run_sim_scenarios import run_scenario, run_variant
from tcp_lab.simulator.scenarios import SCENARIOS, list_scenarios


def find_variant(scenario_id, label):
    for variant in SCENARIOS[scenario_id]["variants"]:
        if variant["label"] == label:
            return variant
    raise KeyError(label)


def test_all_six_scenarios_are_defined():
    ids = []
    for item in list_scenarios():
        ids.append(item["id"])
    # S6Q is the extra queue-vs-delay check for S6 (Phase 5)
    assert ids == ["S1", "S2", "S3", "S4", "S5", "S6", "S6Q"]


def test_aggregate_goodput_never_exceeds_link_rate():
    # 4 flows starting at different times share a 10 Mbps link.
    variant = find_variant("S4", "4_flows")
    for algorithm in ["tahoe", "reno", "newreno"]:
        summary, rows = run_variant(variant, algorithm)
        result = metrics.compute_run_metrics(summary, rows)
        assert result["goodput_mbps"] <= 10.0
        assert result["goodput_mbps"] <= result["throughput_mbps"]
        assert result["num_flows"] == 4


def test_retransmissions_split_into_needed_and_spurious():
    variant = find_variant("S2", "4_losses")
    summary, rows = run_variant(variant, "tahoe")
    result = metrics.compute_run_metrics(summary, rows)
    # Every retransmission that arrived is either needed or spurious
    assert result["needed_retransmissions"] + result["spurious_retransmissions"] \
        <= result["retransmissions"]
    assert result["needed_retransmissions"] == 4      # exactly the 4 scripted drops
    assert result["spurious_retransmissions"] > 0     # go-back-N resends


def test_percentile_and_jain():
    assert metrics.percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert metrics.percentile([], 0.95) is None
    assert metrics.jain_fairness([5.0, 5.0]) == 1.0
    assert metrics.jain_fairness([10.0, 0.0]) == 0.5


def test_runner_writes_csv_json_and_plots(tmp_path):
    run_scenario("S1", ["tahoe", "reno", "newreno"], str(tmp_path))
    variant_dir = os.path.join(str(tmp_path), "S1", "1_loss")
    expected = ["sim_tahoe_events.csv", "sim_reno_events.csv", "sim_newreno_events.csv",
                "timeseries.json", "cwnd.png", "sequence.png", "rtt.png", "throughput.png"]
    for name in expected:
        assert os.path.getsize(os.path.join(variant_dir, name)) > 0

    with open(os.path.join(str(tmp_path), "S1", "summary.json")) as handle:
        summary = json.load(handle)
    assert summary["source"] == "simulator"
    table = summary["variants"][0]["results"]
    assert len(table) == 3
    for row in table:
        assert row["source"] == "simulator"
        assert "goodput_mbps" in row and "throughput_mbps" in row
        assert "spurious_retransmissions" in row
