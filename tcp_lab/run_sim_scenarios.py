"""
Run the simulator scenarios S1 - S6 and save the results.

Usage (from the repository root):
    python -m tcp_lab.run_sim_scenarios                  # every scenario
    python -m tcp_lab.run_sim_scenarios --scenario S2    # just one
    python -m tcp_lab.run_sim_scenarios --scenario S3 --algorithms reno,newreno
    python -m tcp_lab.run_sim_scenarios --seeds 10       # more seeds for random loss

Seeds: a variant with random loss (S3, S6, S6Q) gives a different result for
every random seed, so it is run with seeds 1..N (default 5); Phase 5 reports
the mean, median and spread. Only seed 1 gets the full event CSV and plots;
the other seeds only add a row to the summary. Variants without random loss
(S1, S2, S4, S5) are the same for every seed, so they run once.

Linux-like start: our scenarios start every flow with ssthresh 32, but Linux
starts with NO ssthresh limit, so its first slow start overshoots the queue
and loses a burst of packets. For the scenarios that also run on Mininet
(S3 - S6, S6Q) Reno and New Reno are therefore run a second time with an
unlimited initial ssthresh ("linux_start_results"), only to compare with
Linux. The scores use the normal runs.

Output layout:
    results/<scenario>/<variant>/sim_<algorithm>_events.csv   full event log
    results/<scenario>/<variant>/cwnd.png, sequence.png, rtt.png, throughput.png
    results/<scenario>/<variant>/timeseries.json              downsampled data for the dashboard
    results/<scenario>/summary.json                           summary table, every variant
                                                              ("results" = seed 1,
                                                               "seed_results" = every seed)

Every number written here is labelled "source": "simulator" so it can never
be mixed up with the Mininet (real Linux) measurements.
"""

import argparse
import csv
import json
import os
import time

from tcp_lab.analysis import metrics, plots
from tcp_lab.mininet.scenarios import MININET_SCENARIOS
from tcp_lab.simulator import ALGORITHMS
from tcp_lab.simulator.scenarios import SCENARIOS, has_random_loss
from tcp_lab.simulator.tcp_sim import LOG_COLUMNS, Simulator

DEFAULT_RESULTS_DIR = "results"
DEFAULT_SEEDS = 5
# "no limit" for ssthresh, like Linux at the start of a connection
LINUX_LIKE_SSTHRESH = 1_000_000
LINUX_COMPARISON_ALGORITHMS = ["reno", "newreno"]


def linux_like_start(variant):
    """Copy of a variant whose flows start with an unlimited ssthresh."""
    copy = dict(variant)
    copy["flows"] = []
    for flow in variant["flows"]:
        flow_copy = dict(flow)
        flow_copy["initial_ssthresh"] = LINUX_LIKE_SSTHRESH
        copy["flows"].append(flow_copy)
    return copy


def run_linux_like(variant, algorithms, variant_seeds):
    """Summary rows of the Linux-like-start runs (every seed)."""
    rows = []
    for algorithm in LINUX_COMPARISON_ALGORITHMS:
        if algorithm not in algorithms:
            continue
        for seed in variant_seeds:
            summary, log_rows = run_variant(with_seed(linux_like_start(variant), seed), algorithm)
            row = metrics.compute_run_metrics(summary, log_rows)
            row["algorithm"] = algorithm
            row["source"] = "simulator"
            row["start"] = "linux_like"      # unlimited initial ssthresh
            row["seed"] = seed
            rows.append(row)
    return rows


def with_seed(variant, seed):
    """Copy of a variant with another random seed (the original is not changed)."""
    copy = dict(variant)
    copy["network"] = dict(variant["network"])
    copy["network"]["seed"] = seed
    return copy


def seeds_for(variant, seeds):
    """Seeds 1..N for random-loss variants, just [1] for the others."""
    if not has_random_loss(variant):
        return [1]
    return list(range(1, seeds + 1))


def build_simulator(variant):
    """Create a Simulator from a variant dict (see scenarios.py)."""
    net = variant["network"]
    sim = Simulator(
        bandwidth_mbps=net["bandwidth_mbps"],
        delay_ms=net["delay_ms"],
        queue_size=net["queue_size"],
        loss_rate=net["loss_rate"],
        duration=net["duration"],
        seed=net["seed"],
    )
    for change in variant["changes"]:
        change_time, what, value = change
        if what == "bandwidth":
            sim.change_bandwidth_at(change_time, value)
        elif what == "loss_rate":
            sim.change_loss_rate_at(change_time, value)
        else:
            raise ValueError("Unknown network change: " + what)
    for udp in variant["udp"]:
        sim.add_udp_source(udp["rate_mbps"], udp["start"], udp["stop"])
    return sim


def has_scripted_drops(variant):
    for flow in variant["flows"]:
        if len(flow["scripted_drops"]) > 0:
            return True
    return False


def run_variant(variant, algorithm, log_callback=None):
    """Run one variant with one algorithm. Returns (summary, rows)."""
    sim = build_simulator(variant)
    sim.log_callback = log_callback
    for flow in variant["flows"]:
        sim.add_flow(
            algorithm,
            start_time=flow["start_time"],
            total_segments=flow["total_segments"],
            access_delay_ms=flow["access_delay_ms"],
            initial_cwnd=flow["initial_cwnd"],
            initial_ssthresh=flow["initial_ssthresh"],
            rwnd=flow["rwnd"],
            scripted_drops=flow["scripted_drops"],
        )
    summary = sim.run()
    return summary, sim.log_rows


def write_csv(rows, path):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(data, path):
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2)


def build_timeseries(runs, duration, mss_bytes):
    """Downsampled series per algorithm for the React dashboard."""
    bin_s = plots.pick_bin_size(duration)
    result = {}
    for algorithm in runs:
        rows = runs[algorithm]["rows"]
        result[algorithm] = {
            "cwnd": metrics.cwnd_series(rows, flow_id=0, bin_s=0.02),
            "rtt": metrics.rtt_series(rows, flow_id=0),
            "rate": metrics.rate_series(rows, mss_bytes, duration, bin_s),
            "loss_events": metrics.loss_events(rows, flow_id=0),
        }
    return result


def run_scenario(scenario_id, algorithms, results_dir, make_plots=True, seeds=DEFAULT_SEEDS):
    scenario = SCENARIOS[scenario_id]
    scenario_dir = os.path.join(results_dir, scenario_id)
    os.makedirs(scenario_dir, exist_ok=True)

    scenario_summary = {
        "scenario": scenario_id,
        "name": scenario["name"],
        "description": scenario["description"],
        "source": "simulator",
        "variants": [],
    }

    for variant in scenario["variants"]:
        variant_dir = os.path.join(scenario_dir, variant["label"])
        os.makedirs(variant_dir, exist_ok=True)
        duration = variant["network"]["duration"]

        runs = {}
        table = []
        seed_table = []
        variant_seeds = seeds_for(variant, seeds)
        for algorithm in algorithms:
            started = time.time()
            # seed 1: full event log, plots, timeseries
            summary, rows = run_variant(with_seed(variant, 1), algorithm)
            runs[algorithm] = {"rows": rows, "summary": summary}
            write_csv(rows, os.path.join(variant_dir, "sim_" + algorithm + "_events.csv"))

            row = metrics.compute_run_metrics(summary, rows)
            row["algorithm"] = algorithm
            row["source"] = "simulator"
            row["seed"] = 1
            table.append(row)
            seed_table.append(row)

            # other seeds: only the summary row
            for seed in variant_seeds[1:]:
                seed_summary, seed_rows = run_variant(with_seed(variant, seed), algorithm)
                seed_row = metrics.compute_run_metrics(seed_summary, seed_rows)
                seed_row["algorithm"] = algorithm
                seed_row["source"] = "simulator"
                seed_row["seed"] = seed
                seed_table.append(seed_row)
            print("  %s / %-16s %-8s goodput %6.2f Mbps  throughput %6.2f  retx %4d "
                  "(needed %4d, spurious %4d)  timeouts %3d  [seed 1 of %d, %.1fs]"
                  % (scenario_id, variant["label"], algorithm, row["goodput_mbps"],
                     row["throughput_mbps"], row["retransmissions"],
                     row["needed_retransmissions"], row["spurious_retransmissions"],
                     row["timeouts"], len(variant_seeds), time.time() - started))

        mss_bytes = runs[algorithms[0]]["summary"]["mss_bytes"]
        write_json(build_timeseries(runs, duration, mss_bytes),
                   os.path.join(variant_dir, "timeseries.json"))

        if make_plots:
            title = scenario_id + " " + scenario["name"] + " - " + variant["label"] + " (simulator)"
            plots.plot_cwnd(runs, "cwnd vs time: " + title, os.path.join(variant_dir, "cwnd.png"))
            plots.plot_sequence(runs, "Sequence number vs time: " + title,
                                os.path.join(variant_dir, "sequence.png"))
            # Scripted-loss scenarios: also a zoomed view around the losses
            if has_scripted_drops(variant):
                window = plots.loss_zoom_window(runs, duration)
                if window is not None:
                    plots.plot_sequence(runs, "Sequence number vs time (zoom on losses): " + title,
                                        os.path.join(variant_dir, "sequence_zoom.png"),
                                        time_window=window)
            plots.plot_rtt(runs, "RTT vs time: " + title, os.path.join(variant_dir, "rtt.png"))
            plots.plot_throughput(runs, "Throughput and goodput: " + title,
                                  os.path.join(variant_dir, "throughput.png"),
                                  mss_bytes, duration)

        linux_rows = []
        if scenario_id in MININET_SCENARIOS:
            linux_rows = run_linux_like(variant, algorithms, variant_seeds)

        scenario_summary["variants"].append({
            "label": variant["label"],
            "network": variant["network"],
            "num_flows": len(variant["flows"]),
            "udp": variant["udp"],
            "changes": variant["changes"],
            "results": table,
            "seeds": variant_seeds,
            "seed_results": seed_table,
            "linux_start_results": linux_rows,
        })

    write_json(scenario_summary, os.path.join(scenario_dir, "summary.json"))
    return scenario_summary


def main():
    parser = argparse.ArgumentParser(description="Run TCP Lab simulator scenarios")
    parser.add_argument("--scenario", default="all", help="S1..S6 or 'all'")
    parser.add_argument("--algorithms", default=",".join(ALGORITHMS),
                        help="comma separated, e.g. tahoe,reno,newreno")
    parser.add_argument("--out", default=DEFAULT_RESULTS_DIR, help="results directory")
    parser.add_argument("--no-plots", action="store_true", help="skip PNG plots")
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS,
                        help="seeds per random-loss variant (default 5)")
    args = parser.parse_args()

    algorithms = args.algorithms.split(",")
    if args.scenario == "all":
        scenario_ids = list(SCENARIOS.keys())
    else:
        scenario_ids = [args.scenario]

    for scenario_id in scenario_ids:
        if scenario_id not in SCENARIOS:
            raise SystemExit("Unknown scenario " + scenario_id + ", choose from "
                             + ", ".join(SCENARIOS.keys()))
        print(scenario_id + ": " + SCENARIOS[scenario_id]["name"])
        run_scenario(scenario_id, algorithms, args.out, make_plots=not args.no_plots,
                     seeds=args.seeds)
    print("Results written to " + os.path.abspath(args.out))


if __name__ == "__main__":
    main()
