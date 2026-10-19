"""
Read TCP Lab results from disk for the API (nothing here writes or runs).

Files come from the lab's own scripts (see tcp_lab/README.md):
    results/<S>/summary.json                       simulator ("source": "simulator")
    results/<S>/mininet_summary.json               Mininet   ("source": "mininet")
    results/<S>/<variant>/timeseries.json          simulator time series (seed 1)
    results/<S>/<variant>/mininet_run<N>/ss_*.csv  Mininet ss samples
    results/analysis/analysis.json, *.png          Phase 5 analysis

Safety: every name in a URL is checked against the scenario definitions
(or the list of files actually in the analysis folder) BEFORE it is used
in a path, so a request can never read a file outside results/.

Only standard-library and simulator modules are imported: the API image
does not install matplotlib, so tcp_lab.analysis.plots must not be imported.
"""

import json
import os

from tcp_lab.mininet import ss_sampler
from tcp_lab.mininet.scenarios import MININET_SCENARIOS
from tcp_lab.simulator.scenarios import SCENARIOS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def results_dir():
    """Where the lab writes results; TCP_LAB_RESULTS_DIR overrides it (used by tests)."""
    return os.environ.get("TCP_LAB_RESULTS_DIR", os.path.join(PROJECT_ROOT, "results"))


def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Name checks (raise ValueError -> the route answers 404)
# ---------------------------------------------------------------------------
def check_scenario(scenario_id):
    if scenario_id not in SCENARIOS:
        raise ValueError("Unknown scenario '" + scenario_id + "'")


def check_variant(scenario_id, label):
    check_scenario(scenario_id)
    for variant in SCENARIOS[scenario_id]["variants"]:
        if variant["label"] == label:
            return variant
    raise ValueError("Scenario " + scenario_id + " has no variant '" + label + "'")


# ---------------------------------------------------------------------------
# Scenario list and results
# ---------------------------------------------------------------------------
def list_scenarios():
    """Every scenario, its variants, and which results exist on disk."""
    items = []
    for scenario_id in SCENARIOS:
        scenario = SCENARIOS[scenario_id]
        folder = os.path.join(results_dir(), scenario_id)
        variants = []
        for variant in scenario["variants"]:
            network = variant["network"]
            variants.append({
                "label": variant["label"],
                "bandwidth_mbps": network["bandwidth_mbps"],
                "delay_ms": network["delay_ms"],
                "queue_size": network["queue_size"],
                "loss_rate": network["loss_rate"],
                "duration": network["duration"],
                "num_flows": len(variant["flows"]),
            })
        items.append({
            "id": scenario_id,
            "name": scenario["name"],
            "description": scenario["description"],
            "variants": variants,
            "has_mininet_version": scenario_id in MININET_SCENARIOS,
            "has_simulator_results": os.path.exists(os.path.join(folder, "summary.json")),
            "has_mininet_results": os.path.exists(os.path.join(folder, "mininet_summary.json")),
        })
    return items


def scenario_results(scenario_id):
    """Simulator and Mininet summaries of one scenario (each may be None)."""
    check_scenario(scenario_id)
    folder = os.path.join(results_dir(), scenario_id)
    return {
        "scenario": scenario_id,
        "simulator": read_json(os.path.join(folder, "summary.json")),
        "mininet": read_json(os.path.join(folder, "mininet_summary.json")),
    }


def mininet_run_numbers(scenario_id, label):
    """Run numbers that have a run.json on disk, e.g. [1, 2, 3]."""
    check_variant(scenario_id, label)
    folder = os.path.join(results_dir(), scenario_id, label)
    numbers = []
    if not os.path.isdir(folder):
        return numbers
    for name in sorted(os.listdir(folder)):
        number = name[len("mininet_run"):]
        is_run_folder = name.startswith("mininet_run") and number.isdigit()
        if is_run_folder and os.path.exists(os.path.join(folder, name, "run.json")):
            numbers.append(int(number))
    numbers.sort()
    return numbers


def mininet_cwnd_samples(scenario_id, label, run_number):
    """
    The kernel's cwnd / ssthresh of every flow of one recorded Mininet run,
    from its ss CSVs. Only ESTABLISHED samples (during the handshake Linux
    shows a meaningless default cwnd). Returns a list of dicts in time order:
        {"time", "flow", "cwnd", "ssthresh"}
    Times are seconds after flow 0's first established sample.
    """
    check_variant(scenario_id, label)
    run_dir = os.path.join(results_dir(), scenario_id, label, "mininet_run" + str(int(run_number)))
    run = read_json(os.path.join(run_dir, "run.json"))
    if run is None:
        raise ValueError("No Mininet run " + str(run_number) + " for " + scenario_id + " " + label)
    samples = []
    for flow in run["flows"]:
        local = flow["ss"]["local"]
        if local is None:
            continue
        csv_path = os.path.join(run_dir, "ss_" + flow["client"] + ".csv")
        if not os.path.exists(csv_path):
            continue
        for sample in ss_sampler.samples_of(ss_sampler.read_samples_csv(csv_path), local):
            if sample.get("state") not in (None, "ESTAB") or sample["rtt_ms"] is None:
                continue
            samples.append({"time": sample["time"], "flow": flow["flow"],
                            "cwnd": sample["cwnd"], "ssthresh": sample["ssthresh"]})
    samples.sort(key=lambda item: item["time"])
    # The ss sampler starts about a second before the traffic. Shift the times
    # so flow 0's first established sample is t = 0, like the simulator's
    # start; later flows keep their offset from it (S4 starts them later).
    offset = None
    for sample in samples:
        if sample["flow"] == 0:
            offset = sample["time"]
            break
    if offset is not None:
        for sample in samples:
            sample["time"] = round(sample["time"] - offset, 4)
    return samples


def variant_timeseries(scenario_id, label, mininet_run=1):
    """Simulator time series (seed 1) and the cwnd of one Mininet run, both labelled."""
    check_variant(scenario_id, label)
    folder = os.path.join(results_dir(), scenario_id, label)
    simulator = read_json(os.path.join(folder, "timeseries.json"))
    mininet = None
    if mininet_run in mininet_run_numbers(scenario_id, label):
        mininet = {"source": "mininet", "algorithm": "linux_reno", "run": mininet_run,
                   "cwnd": mininet_cwnd_samples(scenario_id, label, mininet_run)}
    return {
        "scenario": scenario_id,
        "variant": label,
        "simulator": None if simulator is None else {"source": "simulator", "seed": 1,
                                                     "algorithms": simulator},
        "mininet": mininet,
        "mininet_runs": mininet_run_numbers(scenario_id, label),
    }


# ---------------------------------------------------------------------------
# Phase 5 analysis
# ---------------------------------------------------------------------------
def analysis_dir():
    return os.path.join(results_dir(), "analysis")


def analysis():
    return read_json(os.path.join(analysis_dir(), "analysis.json"))


def analysis_plot_path(name):
    """Path of one analysis PNG, only if it is really one of the files there."""
    folder = analysis_dir()
    if not name.endswith(".png") or not os.path.isdir(folder) or name not in os.listdir(folder):
        raise ValueError("No analysis plot '" + name + "'")
    return os.path.join(folder, name)


def analysis_plot_names():
    folder = analysis_dir()
    if not os.path.isdir(folder):
        return []
    names = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".png"):
            names.append(name)
    return names
