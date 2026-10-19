"""
Phase 5: turn the saved results into statistics, scores, a recommendation
and a comparison of the simulator with real Linux (Mininet).

    python -m tcp_lab.run_sim_scenarios            # simulator, 5 seeds for random loss
    (Mininet results: sudo ... run_mininet_scenarios, on the Mininet machine)
    python -m tcp_lab.run_analysis                 # this file

Reads
    results/<S>/summary.json          simulator   ("source": "simulator")
    results/<S>/mininet_summary.json  Mininet     ("source": "mininet")
Writes
    results/analysis/analysis.json    every number below, labelled by source
    results/analysis/report.md        tables, scores, recommendation, S6 explanation
    results/analysis/<S>_comparison.png, s6_goodput_vs_rtt.png

What it does, in order:
  1. collect every run of every variant: one row per SEED (simulator) or
     per RUN (mininet), and add the recovery time to the Mininet rows
     (computed from their pcap time-sequence files)
  2. describe each metric: n, mean, median, std, min, max (stats.py)
  3. score Tahoe / Reno / New Reno on the SIMULATOR numbers only (scoring.py)
  4. compare linux_reno (mininet) with the simulator (compare.py)
  5. explain S6 with the loss formula and the S6Q queue check
"""

import argparse
import csv
import glob
import json
import os

from tcp_lab.analysis import compare, metrics, plots, report, scoring, stats
from tcp_lab.simulator.scenarios import SCENARIOS

DEFAULT_RESULTS_DIR = "results"

SCORED_SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6"]
CHECK_SCENARIOS = ["S6Q"]          # analysed and reported, but not scored

# Every metric that gets mean / median / spread in the report
REPORT_METRICS = [
    "goodput_mbps", "throughput_mbps", "retransmissions", "needed_retransmissions",
    "spurious_retransmissions", "timeouts", "avg_recovery_s", "max_recovery_s",
    "avg_rtt_ms", "p95_rtt_ms", "jain_fairness", "packet_loss_rate",
    "queue_drops", "max_cwnd",
]


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 1. Collecting the rows
# ---------------------------------------------------------------------------
def group_by_algorithm(rows):
    by_algorithm = {}
    for row in rows:
        by_algorithm.setdefault(row["algorithm"], []).append(row)
    return by_algorithm


def simulator_linux_start_rows(summary):
    """{variant label: {algorithm: [rows]}} of the Linux-like-start runs (may be empty)."""
    result = {}
    for variant in summary["variants"]:
        result[variant["label"]] = group_by_algorithm(variant.get("linux_start_results", []))
    return result


def simulator_rows(summary):
    """{variant label: {algorithm: [row per seed]}} from a simulator summary.json."""
    result = {}
    for variant in summary["variants"]:
        rows = variant.get("seed_results")
        if rows is None:
            # summary written before seeds existed: only seed 1
            print("  NOTE: " + summary["scenario"] + " " + variant["label"]
                  + " has no seed_results, re-run run_sim_scenarios for 5 seeds")
            rows = variant["results"]
        result[variant["label"]] = group_by_algorithm(rows)
    return result


def mininet_recovery(run_dir):
    """Recovery episodes of every flow of one Mininet run (from flow<i>_seq.csv)."""
    episodes = []
    for path in sorted(glob.glob(os.path.join(run_dir, "flow*_seq.csv"))):
        with open(path) as handle:
            seq_rows = list(csv.DictReader(handle))
        episodes.extend(metrics.recovery_episodes(metrics.pcap_recovery_events(seq_rows)))
    return metrics.recovery_summary(episodes)


def mininet_max_cwnd(run_dir):
    """Largest cwnd ss saw in this run (all flows), from run.json."""
    run = load_json(os.path.join(run_dir, "run.json"))
    if run is None:
        return None
    values = []
    for flow in run["flows"]:
        if flow["ss"]["max_cwnd"] is not None:
            values.append(flow["ss"]["max_cwnd"])
    if len(values) == 0:
        return None
    return max(values)


def mininet_rows(summary, scenario_dir):
    """{variant label: [row per run]} with recovery time and max cwnd added."""
    result = {}
    for variant in summary["variants"]:
        rows = []
        for row in variant["results"]:
            row = dict(row)
            run_dir = os.path.join(scenario_dir, variant["label"], "mininet_run" + str(row["run"]))
            recovery = mininet_recovery(run_dir)
            for key in recovery:
                row[key] = recovery[key]
            row["max_cwnd"] = mininet_max_cwnd(run_dir)
            rows.append(row)
        result[variant["label"]] = rows
    return result


# ---------------------------------------------------------------------------
# 2 - 4. Statistics, scores, validation for one scenario
# ---------------------------------------------------------------------------
def analyse_scenario(scenario_id, results_dir):
    scenario = SCENARIOS[scenario_id]
    scenario_dir = os.path.join(results_dir, scenario_id)
    sim_summary = load_json(os.path.join(scenario_dir, "summary.json"))
    mn_summary = load_json(os.path.join(scenario_dir, "mininet_summary.json"))
    if sim_summary is None and mn_summary is None:
        return None
    sim = {}
    sim_linux_start = {}
    if sim_summary is not None:
        sim = simulator_rows(sim_summary)
        sim_linux_start = simulator_linux_start_rows(sim_summary)
    mininet = {}
    if mn_summary is not None:
        mininet = mininet_rows(mn_summary, scenario_dir)

    entry = {"scenario": scenario_id, "name": scenario["name"],
             "description": scenario["description"],
             "scored": scenario_id in SCORED_SCENARIOS,
             "has_simulator": sim_summary is not None,
             "has_mininet": mn_summary is not None,
             "variants": []}
    points = {}
    for variant in scenario["variants"]:
        label = variant["label"]
        item = {"label": label, "network": variant["network"],
                "num_flows": len(variant["flows"]),
                "simulator": {}, "simulator_linux_start": {}, "mininet": {},
                "seeds": 0, "mininet_runs": 0,
                "model": compare.model_for_network(variant["network"])}
        for algorithm in sim.get(label, {}):
            rows = sim[label][algorithm]
            item["simulator"][algorithm] = stats.describe_rows(rows, REPORT_METRICS)
            item["seeds"] = len(rows)
        for algorithm in sim_linux_start.get(label, {}):
            item["simulator_linux_start"][algorithm] = stats.describe_rows(
                sim_linux_start[label][algorithm], REPORT_METRICS)
        if label in mininet and len(mininet[label]) > 0:
            item["mininet"]["linux_reno"] = stats.describe_rows(mininet[label], REPORT_METRICS)
            item["mininet_runs"] = len(mininet[label])
            item["mininet_runs_detail"] = mininet[label]

        if entry["scored"] and len(item["simulator"]) > 1:
            item["score"] = scoring.score_variant(item["simulator"], item["num_flows"])
            scoring.add_points(points, item["score"]["points"])
        if len(item["simulator"]) > 0 and len(item["mininet"]) > 0:
            item["validation"] = compare.validate_variant(item["simulator"],
                                                         item["simulator_linux_start"],
                                                         item["mininet"]["linux_reno"])
        entry["variants"].append(item)

    if entry["scored"] and len(points) > 0:
        entry["points"] = points
        entry["winners"] = scoring.best_of(points)
    return entry


# ---------------------------------------------------------------------------
# 5. S6: delay or queue?
# ---------------------------------------------------------------------------
def explain_s6(analysis):
    """Numbers for the S6 explanation: formula, measurements, S6Q queue check."""
    s6 = analysis["scenarios"].get("S6")
    if s6 is None:
        return None
    rows = []
    for item in s6["variants"]:
        row = {"label": item["label"], "model": item["model"]}
        if "newreno" in item["simulator"]:
            row["simulator_newreno_goodput"] = item["simulator"]["newreno"]["goodput_mbps"]
        if "linux_reno" in item["mininet"]:
            row["mininet_goodput"] = item["mininet"]["linux_reno"]["goodput_mbps"]
            # per run: did this run lose a burst from the queue (slow-start overshoot)?
            runs = []
            for run in item["mininet_runs_detail"]:
                runs.append({"run": run["run"], "goodput_mbps": run["goodput_mbps"],
                             "queue_drops": run["queue_drops"], "random_drops": run["random_drops"],
                             "max_cwnd": run["max_cwnd"], "retransmissions": run["retransmissions"]})
            row["mininet_runs"] = runs
        rows.append(row)

    queue_check = []
    s6q = analysis["scenarios"].get("S6Q")
    if s6q is not None:
        for item in s6q["variants"]:
            check = {"label": item["label"], "queue_packets": item["network"]["queue_size"],
                     "loss_rate": item["network"]["loss_rate"]}
            if "newreno" in item["simulator"]:
                check["simulator_newreno_goodput"] = item["simulator"]["newreno"]["goodput_mbps"]
            if "newreno" in item["simulator_linux_start"]:
                check["simulator_newreno_linux_start_goodput"] = (
                    item["simulator_linux_start"]["newreno"]["goodput_mbps"])
            if "linux_reno" in item["mininet"]:
                linux = item["mininet"]["linux_reno"]
                check["mininet_goodput"] = linux["goodput_mbps"]
                # for explaining the no-loss case: overshoot size and repair time
                check["mininet_queue_drops"] = linux["queue_drops"]
                check["mininet_max_cwnd"] = linux["max_cwnd"]
                check["mininet_max_recovery_s"] = linux["max_recovery_s"]
            queue_check.append(check)
    return {"rows": rows, "queue_check": queue_check}


def build_plots(analysis, out_dir):
    for scenario_id in analysis["scenarios"]:
        entry = analysis["scenarios"][scenario_id]
        variants = []
        for item in entry["variants"]:
            variants.append((item["label"], item))
        metrics_to_plot = ["goodput_mbps", "retransmissions", "timeouts", "avg_recovery_s"]
        plots.plot_scenario_comparison(scenario_id, entry["name"], variants, metrics_to_plot,
                                       os.path.join(out_dir, scenario_id + "_comparison.png"))

    s6 = analysis["scenarios"].get("S6")
    if s6 is None:
        return
    points = {}
    for item in s6["variants"]:
        rtt_ms = 2.0 * item["network"]["delay_ms"]
        for algorithm in item["simulator"]:
            points.setdefault((algorithm, "simulator"), []).append(
                (rtt_ms, item["simulator"][algorithm]["goodput_mbps"]))
        if "linux_reno" in item["mininet"]:
            points.setdefault(("linux_reno", "mininet"), []).append(
                (rtt_ms, item["mininet"]["linux_reno"]["goodput_mbps"]))
    network = s6["variants"][0]["network"]
    sim_line = []
    linux_line = []
    for rtt_ms in [10, 15, 20, 30, 50, 70, 100, 150, 200]:
        sim_line.append((rtt_ms, compare.mathis_rate_mbps(
            compare.SIM_MSS_BYTES, rtt_ms / 1000.0, network["loss_rate"], network["bandwidth_mbps"], 1)))
        linux_line.append((rtt_ms, compare.mathis_rate_mbps(
            compare.LINUX_MSS_BYTES, rtt_ms / 1000.0, network["loss_rate"], network["bandwidth_mbps"], 2)))
    plots.plot_goodput_vs_rtt(points, {"Mathis, ACK per segment": sim_line,
                                       "Mathis, delayed ACKs": linux_line},
                              network["bandwidth_mbps"],
                              os.path.join(out_dir, "s6_goodput_vs_rtt.png"))


def analyse_all(results_dir):
    analysis = {"scenarios": {}, "note": "simulator = Python model of Tahoe/Reno/New Reno; "
                "mininet = real Linux reno with SACK off (behaves like New Reno; Linux has "
                "no Tahoe); model = Mathis formula"}
    scenario_scores = {}
    for scenario_id in SCORED_SCENARIOS + CHECK_SCENARIOS:
        entry = analyse_scenario(scenario_id, results_dir)
        if entry is None:
            print("  " + scenario_id + ": no results found, skipped")
            continue
        analysis["scenarios"][scenario_id] = entry
        if "points" in entry:
            scenario_scores[scenario_id] = {"points": entry["points"], "winners": entry["winners"]}
    analysis["recommendation"] = scoring.recommend(scenario_scores)
    analysis["recommendation"]["source"] = "simulator"
    analysis["s6_explanation"] = explain_s6(analysis)
    return analysis


def strip_details(analysis):
    """analysis.json keeps statistics, not the raw per-run rows (except S6's)."""
    for scenario_id in analysis["scenarios"]:
        for item in analysis["scenarios"][scenario_id]["variants"]:
            item.pop("mininet_runs_detail", None)


def main():
    parser = argparse.ArgumentParser(description="TCP Lab analysis (Phase 5)")
    parser.add_argument("--results", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    analysis = analyse_all(args.results)
    if len(analysis["scenarios"]) == 0:
        raise SystemExit("No results in " + args.results + ". Run tcp_lab.run_sim_scenarios first.")
    out_dir = os.path.join(args.results, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    if not args.no_plots:
        build_plots(analysis, out_dir)
    text = report.build_report(analysis)
    with open(os.path.join(out_dir, "report.md"), "w") as handle:
        handle.write(text)
    strip_details(analysis)
    with open(os.path.join(out_dir, "analysis.json"), "w") as handle:
        json.dump(analysis, handle, indent=2)
    print(report.console_summary(analysis))
    print("Written to " + os.path.abspath(out_dir))


if __name__ == "__main__":
    main()
