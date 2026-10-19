"""
Phase 5 tests: statistics over repeated runs, recovery time, scoring,
the simulator-vs-Linux comparison, the Mathis formula and the analysis
runner. Small hand-checkable inputs wherever possible.
"""

import csv
import json
import os

import pytest

from tcp_lab import run_analysis
from tcp_lab.analysis import compare, metrics, scoring, stats
from tcp_lab.run_sim_scenarios import (
    LINUX_LIKE_SSTHRESH,
    linux_like_start,
    run_scenario,
    run_variant,
    seeds_for,
    with_seed,
)
from tcp_lab.simulator.scenarios import SCENARIOS, has_random_loss


def find_variant(scenario_id, label):
    for variant in SCENARIOS[scenario_id]["variants"]:
        if variant["label"] == label:
            return variant
    raise KeyError(label)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def test_describe_real_s6_retransmissions():
    # S6 rtt_10ms on Mininet: one run with a long loss episode
    result = stats.describe([80, 198, 786])
    assert result["n"] == 3
    assert result["mean"] == pytest.approx(354.6667)
    assert result["median"] == 198          # not pulled up by the 786 run
    assert result["min"] == 80 and result["max"] == 786
    # sample std: sqrt((274.67^2 + 156.67^2 + 431.33^2) / 2) = 378.18
    assert result["std"] == pytest.approx(378.18, abs=0.01)


def test_describe_edge_cases():
    assert stats.describe([])["mean"] is None
    assert stats.describe([None, None])["n"] == 0
    single = stats.describe([5.0, None])
    assert single["n"] == 1 and single["std"] == 0.0
    assert stats.format_stats(single) == "5.00"
    assert stats.format_stats(stats.describe([1.0, 2.0, 6.0])) == "3.00 (median 2.00, 1.00-6.00, n=3)"


# ---------------------------------------------------------------------------
# Recovery time
# ---------------------------------------------------------------------------
def test_recovery_episode_by_hand():
    events = [
        (0.0, "send", 1), (0.1, "send", 2), (0.2, "send", 3), (0.3, "send", 4),
        (0.5, "ack", 1),            # segment 2 lost: ACK stays at 1
        (0.6, "retx", 0),           # resend -> episode starts, target = 4
        (0.7, "send", 5),           # new data during recovery does not move the target
        (0.9, "ack", 3),            # partial ACK: not done yet
        (1.0, "ack", 4),            # everything sent before the resend is ACKed
        (2.0, "retx", 0),           # a second loss that never finishes
    ]
    episodes = metrics.recovery_episodes(events)
    assert len(episodes) == 1                     # the open one is left out
    assert episodes[0]["start"] == 0.6
    assert episodes[0]["duration"] == pytest.approx(0.4)
    assert metrics.recovery_summary(episodes) == {
        "recovery_episodes": 1, "avg_recovery_s": 0.4, "max_recovery_s": 0.4}
    assert metrics.recovery_summary([])["avg_recovery_s"] is None


def test_recovery_time_in_the_simulator():
    # S1: one loss, repaired by one fast retransmit -> about one RTT (40 ms + queueing)
    summary, rows = run_variant(find_variant("S1", "1_loss"), "newreno")
    result = metrics.compute_run_metrics(summary, rows)
    assert result["recovery_episodes"] == 1
    assert 0.04 <= result["avg_recovery_s"] <= 0.05
    # S2 with 4 losses in one window: New Reno repairs one hole per RTT (~4 RTTs),
    # Reno needs a timeout and takes longer
    newreno = metrics.compute_run_metrics(*run_variant(find_variant("S2", "4_losses"), "newreno"))
    reno = metrics.compute_run_metrics(*run_variant(find_variant("S2", "4_losses"), "reno"))
    assert 0.15 <= newreno["avg_recovery_s"] <= 0.2
    assert reno["avg_recovery_s"] > newreno["avg_recovery_s"]


def test_recovery_from_pcap_rows():
    # Rows as in a Mininet flow<i>_seq.csv (all strings); byte sequence numbers
    rows = [
        {"time": "1.0", "direction": "DATA", "seq": "0", "len": "100", "ack": "", "retransmission": "0"},
        {"time": "1.1", "direction": "DATA", "seq": "100", "len": "100", "ack": "", "retransmission": "0"},
        {"time": "1.2", "direction": "ACK", "seq": "", "len": "0", "ack": "100", "retransmission": "0"},
        {"time": "1.3", "direction": "DATA", "seq": "100", "len": "100", "ack": "", "retransmission": "1"},
        {"time": "1.4", "direction": "ACK", "seq": "", "len": "0", "ack": "200", "retransmission": "0"},
    ]
    episodes = metrics.recovery_episodes(metrics.pcap_recovery_events(rows))
    assert len(episodes) == 1
    assert episodes[0]["duration"] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def numbers(mean, std, n=5):
    return {"n": n, "mean": mean, "median": mean, "std": std, "min": mean, "max": mean}


def test_clear_win_needs_more_than_the_noise():
    assert scoring.clearly_better(numbers(9.0, 0.1), numbers(8.0, 0.1), "higher")
    # 0.5 better, but the runs scatter by 0.8: not a clear win
    assert not scoring.clearly_better(numbers(9.0, 0.8), numbers(8.5, 0.1), "higher")
    # no randomness (std 0): still needs 2 %, so 9.45 vs 9.44 is a tie
    assert not scoring.clearly_better(numbers(9.45, 0.0, 1), numbers(9.44, 0.0, 1), "higher")
    # "lower is better" metrics
    assert scoring.clearly_better(numbers(0.0, 0.0), numbers(2.0, 0.5), "lower")
    assert not scoring.clearly_better(numbers(0.0, 0.0, 0), numbers(2.0, 0.5), "lower")


def algorithm_stats(goodput, timeouts):
    result = {}
    for metric, _better, _weight, _multi in scoring.SCORE_METRICS:
        result[metric] = numbers(1.0, 0.0)          # equal on everything else
    result["goodput_mbps"] = numbers(goodput, 0.1)
    result["timeouts"] = numbers(timeouts, 0.1)
    return result


def test_score_variant_and_recommendation():
    variant = {"tahoe": algorithm_stats(7.0, 0.0),
               "reno": algorithm_stats(8.0, 3.0),
               "newreno": algorithm_stats(8.0, 0.0)}
    score = scoring.score_variant(variant, num_flows=1)
    # goodput (weight 3): reno and newreno each beat tahoe
    # timeouts (weight 2): tahoe and newreno each beat reno
    assert score["points"] == {"tahoe": 2, "reno": 3, "newreno": 5}
    assert scoring.best_of(score["points"]) == ["newreno"]
    assert scoring.best_of({"reno": 3, "newreno": 3}) == ["reno", "newreno"]

    result = scoring.recommend({"S1": {"points": {"reno": 3, "newreno": 3}, "winners": ["reno", "newreno"]},
                                "S2": {"points": {"reno": 1, "newreno": 6}, "winners": ["newreno"]}})
    assert result["winners"] == ["newreno"]
    assert result["overall_points"] == {"reno": 4, "newreno": 9}
    assert result["scenarios_won"] == {"reno": 1, "newreno": 2}


def test_fairness_only_counts_with_several_flows():
    variant = {"reno": algorithm_stats(8.0, 0.0), "newreno": algorithm_stats(8.0, 0.0)}
    variant["newreno"]["jain_fairness"] = numbers(0.99, 0.0)
    variant["reno"]["jain_fairness"] = numbers(0.70, 0.0)
    assert scoring.score_variant(variant, num_flows=1)["points"]["newreno"] == 0
    assert scoring.score_variant(variant, num_flows=4)["points"]["newreno"] == 1


# ---------------------------------------------------------------------------
# Mathis formula and validation
# ---------------------------------------------------------------------------
def test_mathis_formula_numbers():
    # 0.5 % loss: average window 1.22 / sqrt(0.005) = 17.3 segments (12.2 with delayed ACKs)
    assert compare.mathis_window_segments(0.005, 1) == pytest.approx(17.32, abs=0.01)
    assert compare.mathis_window_segments(0.005, 2) == pytest.approx(12.25, abs=0.01)
    # 50 ms RTT: 17.3 x 1460 B x 8 / 0.05 s = 4.05 Mbit/s
    assert compare.mathis_rate_mbps(1460, 0.05, 0.005, 10.0) == pytest.approx(4.05, abs=0.01)
    # 10 ms RTT: the formula says 20 Mbit/s, but the link is only 10
    assert compare.mathis_rate_mbps(1460, 0.01, 0.005, 10.0) == 10.0
    assert compare.bdp_segments(10.0, 0.05, 1460) == pytest.approx(42.8, abs=0.1)


def test_model_only_for_random_loss():
    assert compare.model_for_network(find_variant("S4", "1_flow")["network"]) is None
    model = compare.model_for_network(find_variant("S6", "rtt_50ms")["network"])
    assert model["source"] == "model"
    assert model["base_rtt_ms"] == 50.0
    assert model["bdp_segments"] > model["loss_window_segments"]    # loss-limited


def test_validation_row():
    sim = {"newreno": {"goodput_mbps": numbers(9.6, 0.0), "timeouts": numbers(0.0, 0.0)}}
    linux_start = {"newreno": {"goodput_mbps": numbers(7.4, 0.0), "timeouts": numbers(0.0, 0.0)},
                   "reno": {"goodput_mbps": numbers(9.3, 0.0), "timeouts": numbers(1.0, 0.0)}}
    mininet = {"goodput_mbps": stats.describe([6.97, 7.08, 6.97]),
               "timeouts": stats.describe([0, 0, 0]),
               "spurious_retransmissions": stats.describe([0, 0, 0])}
    row = compare.validate_variant(sim, linux_start, mininet)
    assert row["closer_by_goodput"] == "newreno"
    assert row["goodput_vs_newreno_linux_start_pct"] == pytest.approx(-5.3, abs=0.1)
    assert row["timeouts_vs_simulator"] == "between"
    assert compare.compare_to_pair(5.3, 1.2, 2.2) == "more than both"
    assert compare.compare_to_pair(0.3, 1.0, 1.0) == "fewer than both"


# ---------------------------------------------------------------------------
# Seeds and the Linux-like start in the simulator runner
# ---------------------------------------------------------------------------
def test_only_random_loss_variants_get_several_seeds():
    assert has_random_loss(find_variant("S3", "loss_1pct"))
    assert not has_random_loss(find_variant("S4", "2_flows"))
    assert seeds_for(find_variant("S3", "loss_1pct"), 5) == [1, 2, 3, 4, 5]
    assert seeds_for(find_variant("S5", "step_down_up"), 5) == [1]


def test_seed_and_linux_start_copies_do_not_change_the_scenario():
    variant = find_variant("S3", "loss_1pct")
    copy = linux_like_start(with_seed(variant, 4))
    assert copy["network"]["seed"] == 4
    assert copy["flows"][0]["initial_ssthresh"] == LINUX_LIKE_SSTHRESH
    assert variant["network"]["seed"] == 1
    assert variant["flows"][0]["initial_ssthresh"] == 32


def test_different_seeds_give_different_random_loss():
    variant = find_variant("S3", "loss_1pct")
    first = metrics.compute_run_metrics(*run_variant(with_seed(variant, 1), "newreno"))
    second = metrics.compute_run_metrics(*run_variant(with_seed(variant, 2), "newreno"))
    again = metrics.compute_run_metrics(*run_variant(with_seed(variant, 1), "newreno"))
    assert first["goodput_mbps"] == again["goodput_mbps"]          # repeatable
    assert first["goodput_mbps"] != second["goodput_mbps"]


# ---------------------------------------------------------------------------
# The analysis runner, end to end on small data
# ---------------------------------------------------------------------------
def write_fake_mininet_s1(results_dir):
    """A tiny Mininet-style summary for S1, with one run dir (seq CSV + run.json)."""
    run_dir = os.path.join(results_dir, "S1", "1_loss", "mininet_run1")
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "flow0_seq.csv"), "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "direction", "seq", "len", "ack",
                                                    "window", "retransmission", "dupack",
                                                    "dupack_count"])
        writer.writeheader()
        for time_s, direction, seq, length, ack, retx in [
                ("0.0", "DATA", "0", "100", "", "0"), ("0.1", "DATA", "100", "100", "", "0"),
                ("0.2", "DATA", "100", "100", "", "1"), ("0.25", "ACK", "", "0", "200", "0")]:
            writer.writerow({"time": time_s, "direction": direction, "seq": seq, "len": length,
                             "ack": ack, "window": "1000", "retransmission": retx,
                             "dupack": "0", "dupack_count": "0"})
    with open(os.path.join(run_dir, "run.json"), "w") as handle:
        json.dump({"flows": [{"ss": {"max_cwnd": 42.0}}]}, handle)
    row = {"source": "mininet", "algorithm": "linux_reno", "run": 1, "goodput_mbps": 8.0,
           "throughput_mbps": 8.1, "retransmissions": 1, "spurious_retransmissions": 0,
           "timeouts": 0, "queue_drops": 0, "random_drops": 0}
    with open(os.path.join(results_dir, "S1", "mininet_summary.json"), "w") as handle:
        json.dump({"scenario": "S1", "source": "mininet",
                   "variants": [{"label": "1_loss", "results": [row]}]}, handle)


def test_analysis_runner_end_to_end(tmp_path, monkeypatch):
    results_dir = str(tmp_path)
    run_scenario("S1", ["tahoe", "reno", "newreno"], results_dir, make_plots=False)
    write_fake_mininet_s1(results_dir)
    monkeypatch.setattr("sys.argv", ["run_analysis", "--results", results_dir, "--no-plots"])
    run_analysis.main()

    with open(os.path.join(results_dir, "analysis", "analysis.json")) as handle:
        analysis = json.load(handle)
    s1 = analysis["scenarios"]["S1"]
    item = s1["variants"][0]
    assert item["simulator"]["newreno"]["goodput_mbps"]["n"] == 1
    linux = item["mininet"]["linux_reno"]
    assert linux["goodput_mbps"]["mean"] == 8.0
    # recovery time and max cwnd were added from the run's files
    assert linux["avg_recovery_s"]["mean"] == pytest.approx(0.05)
    assert linux["max_cwnd"]["mean"] == 42.0
    assert analysis["recommendation"]["source"] == "simulator"
    assert set(s1["winners"]) <= {"tahoe", "reno", "newreno"}

    with open(os.path.join(results_dir, "analysis", "report.md")) as handle:
        text = handle.read()
    assert "Recommended:" in text
    assert "(simulator)" in text and "(mininet)" in text


def test_no_loss_sentence_uses_the_numbers():
    from tcp_lab.analysis import report
    check = {"label": "rtt_50ms_no_loss", "loss_rate": 0.0, "queue_packets": 100,
             "mininet_goodput": stats.describe([5.87, 5.66, 6.03]),
             "simulator_newreno_goodput": stats.describe([9.572]),
             "simulator_newreno_linux_start_goodput": stats.describe([6.2543]),
             "mininet_max_cwnd": stats.describe([273, 273, 274]),
             "mininet_queue_drops": stats.describe([174, 184, 171]),
             "mininet_max_recovery_s": stats.describe([7.31, 7.31, 7.26])}
    text = " ".join(report.no_loss_sentences([check]))
    assert "about 5.9 Mbit/s at 50 ms RTT, against 9.57 in the simulator" in text
    assert "max cwnd 273 segments, 176 queue drops" in text
    assert "lasts 7.3 s" in text
    assert "gets 6.25 Mbit/s" in text
    # without Mininet numbers nothing is claimed
    del check["mininet_goodput"]
    assert report.no_loss_sentences([check]) == []
