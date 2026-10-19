"""
Run scenarios S3 - S6 (and the S6Q queue check) with REAL Linux TCP
(reno, SACK off) in Mininet.

    sudo python3 -m tcp_lab.run_mininet_scenarios                    # S3-S6 + S6Q, 3 runs each
    sudo python3 -m tcp_lab.run_mininet_scenarios --scenario S3 --runs 5
    sudo python3 -m tcp_lab.run_mininet_scenarios --scenario S4 --variant 2_flows
    sudo python3 -m tcp_lab.run_mininet_scenarios --controller ryu   # switches under Ryu
(or use scripts/run_tcp_lab_mininet.sh, which also gives the files back to you)

Every variant is run several times (--runs, default 3), because real runs
are not repeatable: timer and scheduling noise changes when packets are
lost. Run N uses netem seed N, so its random loss pattern can be repeated.
Phase 5 averages the runs.

One run, step by step:
  1. put the tc conditions on the bottleneck (fresh qdiscs = fresh counters)
  2. start an iperf3 server per flow (and per UDP source)
  3. start tcpdump on every client and server, and the ss sampler on
     every client; read the nstat counters of every client
  4. start each flow / UDP source at its start time; the S5 bandwidth
     steps run in a background thread
  5. wait for the flows, read nstat again, stop the captures
  6. parse everything and write one row of results

Output (next to the simulator results, never overwriting them):
  results/<S>/<variant>/mininet_run<N>/       raw files of run N
      flow<i>_iperf3.json   udp<j>_iperf3.json   ss_<client>.csv
      <host>.pcap           flow<i>_seq.csv (time-sequence, sender side)
      run.json              everything parsed from this run
  results/<S>/mininet_summary.json            one result row per run

Every file says "source": "mininet" and "algorithm": "linux_reno".

Where each number comes from (also stored in the rows):
  goodput        iperf3 server: bytes the application read / experiment length
  throughput     pcap at the SERVER: payload bytes that arrived, resends included
  retransmissions  iperf3 (sender kernel); nstat and the sender pcap as checks
  spurious       pcap at the server: resent data the receiver had already ACKed
  timeouts, fast retransmits, recoveries   nstat on the clients
  queue / random drops   tc statistics of the bottleneck qdiscs
  RTT            ss (the kernel's smoothed RTT), sampled every 50 ms
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from tcp_lab.analysis import metrics
from tcp_lab.mininet import (
    cleanup,
    host_setup,
    pcap_parser,
    scenarios,
    ss_sampler,
    tc_controller,
    traffic,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
REQUIRED_TOOLS = ["iperf3", "tcpdump", "ss", "nstat", "ethtool", "tc"]
ALGORITHM = "linux_reno"
SOURCE = "mininet"
INITCWND = 1          # every connection must start with cwnd = 1 segment


class SetupError(Exception):
    """A run measured something other than the lab's TCP settings: stop everything."""


def write_json(data, path):
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2)


def read_json_file(path):
    with open(path) as handle:
        return handle.read()


def popen_to_file(node, command, out_path):
    """Start a process on a Mininet node with its output going to a file."""
    handle = open(out_path, "w")  # noqa: SIM115 - closed by stop_processes()
    process = node.popen(command, stdout=handle, stderr=handle, cwd=PROJECT_ROOT)
    return {"process": process, "file": handle, "name": os.path.basename(out_path)}


def stop_processes(started):
    """Stop background processes (tcpdump, leftover servers) and close their files."""
    for item in started:
        if item["process"].poll() is None:
            item["process"].terminate()
    for item in started:
        try:
            item["process"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            item["process"].kill()
        item["file"].close()


def hosts_in_plan(plan):
    """Names of the clients and servers this plan uses (each only once)."""
    clients = []
    servers = []
    for item in plan["flows"] + plan["udp"]:
        if item["client"] not in clients:
            clients.append(item["client"])
        if item["server"] not in servers:
            servers.append(item["server"])
    return clients, servers


def build_schedule(plan):
    """Flows and UDP sources in the order they start."""
    schedule = []
    for flow in plan["flows"]:
        schedule.append({"kind": "tcp", "item": flow})
    for udp in plan["udp"]:
        schedule.append({"kind": "udp", "item": udp})
    # sort by start time (simple insertion sort, the list has at most ~7 entries)
    ordered = []
    for entry in schedule:
        position = 0
        while position < len(ordered) and ordered[position]["item"]["start"] <= entry["item"]["start"]:
            position = position + 1
        ordered.insert(position, entry)
    return ordered


def with_seed(conditions, seed):
    return tc_controller.merged_conditions(conditions, {"seed": seed})


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------
def run_once(net, info, plan, run_dir, seed):
    """Run one plan once. Returns the raw measurements (parsed later)."""
    os.makedirs(run_dir, exist_ok=True)
    clients, servers = hosts_in_plan(plan)
    forward_switch, forward_interface = info["forward_interfaces"][0]
    reverse_switch, reverse_interface = info["reverse_interfaces"][0]

    # 1) Fresh qdiscs on the bottleneck: deleting first resets the tc counters
    forward = with_seed(plan["forward"], seed)
    net.get(forward_switch).cmd(tc_controller.build_clear_command(forward_interface))
    net.get(reverse_switch).cmd(tc_controller.build_clear_command(reverse_interface))
    tc_controller.apply_conditions(net.get(forward_switch), forward_interface, forward)
    tc_controller.apply_conditions(net.get(reverse_switch), reverse_interface, plan["reverse"])

    background = []      # tcpdump, ss sampler, servers: stopped at the end
    # 2) One iperf3 server per flow / UDP source (-1: exits after its test)
    for item in plan["flows"] + plan["udp"]:
        kind = "flow" if "flow" in item else "udp"
        number = item["flow"] if kind == "flow" else item["udp"]
        background.append(popen_to_file(
            net.get(item["server"]), traffic.iperf3_server_cmd(item["port"]),
            os.path.join(run_dir, kind + str(number) + "_server.log")))

    # 3) Captures on every host involved, ss sampler on every client
    for name in clients + servers:
        host = net.get(name)
        background.append(popen_to_file(
            host, traffic.tcpdump_cmd(host.intfNames()[0], os.path.join(run_dir, name + ".pcap")),
            os.path.join(run_dir, name + "_tcpdump.log")))
    samplers = []
    for name in clients:
        sampler = popen_to_file(
            net.get(name),
            [sys.executable, "-m", "tcp_lab.mininet.ss_sampler", "--dst", "10.0.0.0/24",
             "--duration", str(plan["duration"] + 3),
             "--out", os.path.join(run_dir, "ss_" + name + ".csv")],
            os.path.join(run_dir, "ss_" + name + ".log"))
        samplers.append(sampler)
    nstat_before = {}
    for name in clients:
        nstat_before[name] = traffic.parse_nstat(net.get(name).cmd(traffic.NSTAT_CMD))
    time.sleep(1.0)     # let tcpdump and the servers get ready

    # 4) Start everything on schedule; tc changes in their own thread
    start_time = time.time()
    tc_changes = []
    tc_thread = None
    if len(plan["timeline"]) > 0:
        tc_thread = threading.Thread(
            target=tc_controller.run_timeline,
            args=(net.get(forward_switch), forward_interface, plan["timeline"],
                  start_time, tc_changes))
        tc_thread.start()

    senders = []
    for entry in build_schedule(plan):
        item = entry["item"]
        wait = start_time + item["start"] - time.time()
        if wait > 0:
            time.sleep(wait)
        if entry["kind"] == "tcp":
            command = traffic.iperf3_tcp_client_cmd(item["server_ip"], round(item["duration"]),
                                                    port=item["port"])
            out_path = os.path.join(run_dir, "flow" + str(item["flow"]) + "_iperf3.json")
        else:
            command = traffic.iperf3_udp_client_cmd(item["server_ip"], item["rate_mbps"],
                                                    round(item["duration"]), port=item["port"])
            out_path = os.path.join(run_dir, "udp" + str(item["udp"]) + "_iperf3.json")
        sender = popen_to_file(net.get(item["client"]), command, out_path)
        sender["started_at"] = round(time.time() - start_time, 3)
        senders.append(sender)

    # 5) Wait for all senders (with a safety limit), then collect counters
    for sender in senders:
        try:
            sender["process"].wait(timeout=plan["duration"] + 30)
        except subprocess.TimeoutExpired:
            print("  WARNING: " + sender["name"] + " did not finish, killing it")
            sender["process"].kill()
        sender["file"].close()
    if tc_thread is not None:
        tc_thread.join()
    nstat = {}
    for name in clients:
        after = traffic.parse_nstat(net.get(name).cmd(traffic.NSTAT_CMD))
        nstat[name] = traffic.diff_counters(nstat_before[name], after)
    for sampler in samplers:
        sampler["process"].wait()
    time.sleep(0.5)     # last ACKs reach tcpdump
    stop_processes(background + samplers)

    tc_stats = tc_controller.parse_tc_stats(
        net.get(forward_switch).cmd(tc_controller.build_stats_command(forward_interface)))

    started = {}
    for sender in senders:
        started[sender["name"]] = sender["started_at"]
    return {"seed": seed, "nstat": nstat, "tc_stats": tc_stats, "tc_changes": tc_changes,
            "started_at": started, "clients": clients, "servers": servers}


# ---------------------------------------------------------------------------
# Turning the raw files of one run into numbers
# ---------------------------------------------------------------------------
def bottleneck_drops(tc_stats):
    """
    The root netem's counters include its tbf child (in a real run both
    showed the same 130 drops with no random loss configured). So:
      queue drops  = tbf dropped        (queue full, drop-tail)
      random drops = netem - tbf        (netem's own random loss)
    """
    netem = None
    tbf = None
    for qdisc in tc_stats:
        if qdisc["kind"] == "netem":
            netem = qdisc
        elif qdisc["kind"] == "tbf":
            tbf = qdisc
    if netem is None:
        return {"queue_drops": None, "random_drops": None, "packets_offered": None}
    queue_drops = 0
    if tbf is not None:
        queue_drops = tbf["dropped"]
    return {"queue_drops": queue_drops,
            "random_drops": netem["dropped"] - queue_drops,
            # every packet that reached the bottleneck was either sent or dropped
            "packets_offered": netem["sent_packets"] + netem["dropped"]}


def parse_flow(flow, run_dir, pcaps):
    """All measurements of one TCP flow, labelled by where they came from."""
    name = "flow" + str(flow["flow"])
    result = {"flow": flow["flow"], "client": flow["client"], "server": flow["server"],
              "port": flow["port"], "start": flow["start"]}

    # iperf3: goodput (what the server application read) and retransmissions
    iperf3_path = os.path.join(run_dir, name + "_iperf3.json")
    try:
        result["iperf3"] = traffic.parse_iperf3_tcp(read_json_file(iperf3_path))
    except (ValueError, RuntimeError, KeyError) as error:
        print("  WARNING: " + name + ": iperf3 report unreadable: " + str(error))
        result["iperf3"] = None

    # pcap at the sender: what was sent (time-sequence CSV for the plots)
    sender_packets = pcaps[flow["client"]]
    connection = pcap_parser.find_flow_to(sender_packets, flow["client_ip"],
                                          flow["server_ip"], flow["port"])
    result["pcap_sender"] = None
    result["pcap_receiver"] = None
    result["spurious"] = None
    if connection is not None:
        rows, summary = pcap_parser.analyse_flow(sender_packets, connection)
        pcap_parser.write_sequence_csv(rows, os.path.join(run_dir, name + "_seq.csv"))
        result["pcap_sender"] = summary
        # pcap at the receiver: what arrived, and which resends were not needed
        receiver_packets = pcaps[flow["server"]]
        _rows, summary = pcap_parser.analyse_flow(receiver_packets, connection)
        result["pcap_receiver"] = summary
        result["spurious"] = pcap_parser.count_spurious_at_receiver(receiver_packets, connection)

    # ss: the kernel's own cwnd / ssthresh / RTT for this socket
    samples = ss_sampler.read_samples_csv(os.path.join(run_dir, "ss_" + flow["client"] + ".csv"))
    local = ss_sampler.pick_flow_to(samples, flow["server_ip"], flow["port"])
    flow_samples = ss_sampler.samples_of(samples, local)
    rtts = []
    for sample in flow_samples:
        if sample["rtt_ms"] is not None:
            rtts.append(sample["rtt_ms"])
    result["ss"] = {"local": local, "samples": len(flow_samples),
                    # the cwnd the connection started with (see ss_sampler.estimate_initial_cwnd)
                    "initial_cwnd": ss_sampler.estimate_initial_cwnd(flow_samples),
                    "first_established": None,
                    "max_cwnd": None, "retrans_total": None, "rtt_ms": rtts}
    first = ss_sampler.first_established_sample(flow_samples)
    if first is not None:
        result["ss"]["first_established"] = {"time": first["time"], "cwnd": first["cwnd"],
                                             "delivered": first.get("delivered")}
    if len(flow_samples) > 0:
        cwnds = []
        for sample in flow_samples:
            if sample["cwnd"] is not None and sample.get("state") in (None, "ESTAB"):
                cwnds.append(sample["cwnd"])
        if len(cwnds) > 0:
            result["ss"]["max_cwnd"] = max(cwnds)
        result["ss"]["retrans_total"] = flow_samples[-1]["retrans_total"]
    return result


def check_initial_cwnd(flows, wanted=INITCWND):
    """
    Did every flow really start with cwnd = `wanted`?
    Returns (failures, unknown): two lists of messages. A failure means the
    run did not use the lab's settings; unknown means it could not be
    checked (e.g. a loss happened before the first ss sample).
    """
    failures = []
    unknown = []
    for flow in flows:
        name = "flow" + str(flow["flow"]) + " (" + flow["client"] + " -> " + flow["server"] + ")"
        estimate = flow["ss"]["initial_cwnd"]
        if estimate is None:
            unknown.append(name + ": initial cwnd could not be worked out from ss")
        elif estimate != wanted:
            first = flow["ss"]["first_established"]
            # (with Linux's default initcwnd 10 the estimate shows 9 or 10: iperf3's
            # first 37-byte segment does not fill the window, so cwnd does not grow)
            failures.append(name + ": initial cwnd estimated as " + str(estimate) + ", expected "
                            + str(wanted) + " (first established ss sample: " + str(first) + ")")
    return failures, unknown


def parse_udp(udp, run_dir):
    path = os.path.join(run_dir, "udp" + str(udp["udp"]) + "_iperf3.json")
    try:
        report = traffic.parse_iperf3_udp(read_json_file(path))
    except (ValueError, RuntimeError, KeyError) as error:
        print("  WARNING: udp" + str(udp["udp"]) + ": iperf3 report unreadable: " + str(error))
        report = None
    return {"udp": udp["udp"], "rate_mbps": udp["rate_mbps"], "start": udp["start"],
            "iperf3": report}


def add_up(values):
    """Sum that gives None if any value is missing (instead of a wrong total)."""
    total = 0
    for value in values:
        if value is None:
            return None
        total = total + value
    return total


def build_result_row(plan, raw, flows, udp, run_number):
    """One row of the summary table, same names as the simulator's rows."""
    duration = plan["duration"]

    received_bytes = []
    arrived_bytes = []
    retrans_iperf3 = []
    retrans_pcap = []
    spurious = []
    per_flow_goodput = []
    rtts = []
    initial_cwnds = []
    for flow in flows:
        initial_cwnds.append(flow["ss"]["initial_cwnd"])
        if flow["iperf3"] is not None:
            received_bytes.append(flow["iperf3"]["received_bytes"])
            retrans_iperf3.append(flow["iperf3"]["retransmits"])
            per_flow_goodput.append(round(flow["iperf3"]["goodput_mbps"], 4))
        else:
            received_bytes.append(None)
            retrans_iperf3.append(None)
        if flow["pcap_sender"] is not None:
            retrans_pcap.append(flow["pcap_sender"]["retransmissions"])
            arrived_bytes.append(flow["pcap_receiver"]["data_bytes"])
            spurious.append(flow["spurious"]["spurious_retransmissions"])
        else:
            retrans_pcap.append(None)
            arrived_bytes.append(None)
            spurious.append(None)
        rtts.extend(flow["ss"]["rtt_ms"])

    nstat_retrans = []
    timeouts = []
    fast_retransmits = []
    recoveries = []
    recovery_failures = []
    for name in raw["nstat"]:
        counters = raw["nstat"][name]
        nstat_retrans.append(counters["TcpRetransSegs"])
        timeouts.append(counters["TcpExtTCPTimeouts"])
        fast_retransmits.append(counters["TcpExtTCPFastRetrans"])
        recoveries.append(counters["TcpExtTCPRenoRecovery"])
        recovery_failures.append(counters["TcpExtTCPRenoRecoveryFail"])

    total_received = add_up(received_bytes)
    total_arrived = add_up(arrived_bytes)
    retransmissions = add_up(retrans_iperf3)
    spurious_total = add_up(spurious)
    drops = bottleneck_drops(raw["tc_stats"])

    row = {
        "source": SOURCE,
        "algorithm": ALGORITHM,
        "run": run_number,
        "netem_seed": raw["seed"],
        "num_flows": len(flows),
        "duration_s": duration,
        # goodput: bytes the iperf3 servers read, over the whole experiment
        "goodput_mbps": None,
        # throughput: payload bytes that reached the servers, resends included
        "throughput_mbps": None,
        "retransmissions": retransmissions,
        "retransmissions_by_source": {"iperf3": retransmissions,
                                      "nstat": add_up(nstat_retrans),
                                      "pcap": add_up(retrans_pcap)},
        "spurious_retransmissions": spurious_total,
        "needed_retransmissions": None,
        "timeouts": add_up(timeouts),
        "fast_retransmits": add_up(fast_retransmits),
        "recoveries": add_up(recoveries),
        "recovery_failures": add_up(recovery_failures),
        "queue_drops": drops["queue_drops"],
        "random_drops": drops["random_drops"],
        "packet_loss_rate": None,
        "avg_rtt_ms": metrics.average(rtts),
        "p95_rtt_ms": metrics.percentile(rtts, 0.95),
        "per_flow_goodput_mbps": per_flow_goodput,
        "jain_fairness": metrics.jain_fairness(per_flow_goodput),
        "initial_cwnd": initial_cwnds,
        # UDP background (S4): what each UDP source got through, by the iperf3 server
        "udp_received_mbps": [],
    }
    for source in udp:
        if source["iperf3"] is None:
            row["udp_received_mbps"].append(None)
        else:
            row["udp_received_mbps"].append(round(source["iperf3"]["received_mbps"], 4))
    if total_received is not None:
        row["goodput_mbps"] = total_received * 8 / duration / 1e6
    if total_arrived is not None:
        row["throughput_mbps"] = total_arrived * 8 / duration / 1e6
    if retransmissions is not None and spurious_total is not None:
        # needed = every resend the receiver did NOT already have
        row["needed_retransmissions"] = retransmissions - spurious_total
    if drops["packets_offered"]:
        # all drops at the bottleneck (UDP packets too, in S4) / packets offered to it
        row["packet_loss_rate"] = ((drops["queue_drops"] + drops["random_drops"])
                                   / drops["packets_offered"])
    for key in row:
        if isinstance(row[key], float):
            row[key] = round(row[key], 4)
    return row


def parse_run(plan, raw, run_dir, run_number):
    pcaps = {}
    for name in raw["clients"] + raw["servers"]:
        pcaps[name] = pcap_parser.read_pcap(os.path.join(run_dir, name + ".pcap"))
    flows = []
    for flow in plan["flows"]:
        flows.append(parse_flow(flow, run_dir, pcaps))
    udp = []
    for source in plan["udp"]:
        udp.append(parse_udp(source, run_dir))
    row = build_result_row(plan, raw, flows, udp, run_number)

    # run.json keeps everything except the long RTT lists (they are in the ss CSVs)
    for flow in flows:
        flow["ss"]["rtt_samples"] = len(flow["ss"]["rtt_ms"])
        del flow["ss"]["rtt_ms"]
    write_json({"source": SOURCE, "algorithm": ALGORITHM, "run": run_number, "plan": plan,
                "raw": raw, "flows": flows, "udp": udp, "result": row},
               os.path.join(run_dir, "run.json"))
    return row, flows


# ---------------------------------------------------------------------------
# A whole scenario
# ---------------------------------------------------------------------------
def load_summary(path, scenario):
    """Earlier summary of this scenario (so --variant only replaces its own entry)."""
    if os.path.exists(path):
        with open(path) as handle:
            return json.load(handle)
    return {"scenario": scenario["id"], "name": scenario["name"],
            "description": scenario["description"], "source": SOURCE,
            "algorithm": ALGORITHM, "variants": []}


def store_variant(summary, entry):
    """Replace the entry with the same label, or add it."""
    for index in range(len(summary["variants"])):
        if summary["variants"][index]["label"] == entry["label"]:
            summary["variants"][index] = entry
            return
    summary["variants"].append(entry)


def run_scenario(net, info, scenario_id, runs, results_dir, only_variant=None, controller=""):
    scenario = scenarios.get_scenario(scenario_id)
    scenario_dir = os.path.join(results_dir, scenario_id)
    os.makedirs(scenario_dir, exist_ok=True)
    summary_path = os.path.join(scenario_dir, "mininet_summary.json")
    summary = load_summary(summary_path, scenario)

    for plan in scenario["plans"]:
        if only_variant is not None and plan["label"] != only_variant:
            continue
        rows = []
        for run_number in range(1, runs + 1):
            run_dir = os.path.join(scenario_dir, plan["label"], "mininet_run" + str(run_number))
            started = time.time()
            raw = run_once(net, info, plan, run_dir, seed=run_number)
            row, flows = parse_run(plan, raw, run_dir, run_number)
            by_source = row["retransmissions_by_source"]
            print("  %s / %-16s run %d  goodput %s Mbps  throughput %s  retx %s "
                  "(iperf3/nstat/pcap %s/%s/%s, spurious %s)  timeouts %s  initial cwnd %s  [%.0fs]"
                  % (scenario_id, plan["label"], run_number, row["goodput_mbps"],
                     row["throughput_mbps"], row["retransmissions"], by_source["iperf3"],
                     by_source["nstat"], by_source["pcap"], row["spurious_retransmissions"],
                     row["timeouts"], row["initial_cwnd"], time.time() - started))
            failures, unknown = check_initial_cwnd(flows)
            for message in unknown:
                print("  WARNING: " + message)
            if len(failures) > 0:
                # This run is not valid data: do not store it, stop everything
                raise SetupError("initial cwnd check FAILED in " + scenario_id + " / "
                                 + plan["label"] + " run " + str(run_number) + ":\n    "
                                 + "\n    ".join(failures))
            rows.append(row)
            time.sleep(1.0)   # let TIME_WAIT sockets and queues drain
        store_variant(summary, {
            "label": plan["label"],
            "plan": plan,
            "runs": runs,
            "controller": controller,
            "results": rows,
        })
        write_json(summary, summary_path)    # after every variant: a crash keeps the rest
    return summary


def check_environment():
    problems = []
    if os.geteuid() != 0:
        problems.append("must run as root (sudo python3 -m tcp_lab.run_mininet_scenarios)")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            problems.append("missing tool: " + tool)
    return problems


def warm_up(net, info):
    """Ping every client -> server pair once, so ARP and MAC learning are done."""
    for client in info["clients"]:
        for server in info["servers"]:
            net.get(client["name"]).cmd("ping -c 1 -W 1 " + server["ip"])


def main():
    parser = argparse.ArgumentParser(description="Run TCP Lab scenarios on Mininet (Linux reno)")
    parser.add_argument("--scenario", default="all",
                        help=", ".join(scenarios.MININET_SCENARIOS) + " or 'all'")
    parser.add_argument("--variant", default=None, help="run only this variant label")
    parser.add_argument("--runs", type=int, default=3, help="repetitions per variant (default 3)")
    parser.add_argument("--controller", choices=["standalone", "ryu"], default="standalone")
    parser.add_argument("--out", default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args()

    if args.scenario == "all":
        scenario_ids = list(scenarios.MININET_SCENARIOS)
    else:
        scenario_ids = [args.scenario]
    for scenario_id in scenario_ids:
        if scenario_id not in scenarios.MININET_SCENARIOS:
            print("ERROR: " + scenario_id + " has no Mininet version (S1/S2 need one chosen "
                  "segment dropped, which netem cannot do). Choose from "
                  + ", ".join(scenarios.MININET_SCENARIOS))
            return 1
    if args.runs < 1:
        print("ERROR: --runs must be at least 1")
        return 1
    problems = check_environment()
    if len(problems) > 0:
        for problem in problems:
            print("ERROR: " + problem)
        return 1

    # Imported here so the errors above are shown even where Mininet is missing
    from mininet.log import setLogLevel

    from tcp_lab.mininet import dumbbell_topo

    setLogLevel("warning")
    cleanup.cleanup_lab("dumbbell", verbose=False)
    net = dumbbell_topo.build_dumbbell_net(controller=args.controller)
    info = dumbbell_topo.dumbbell_info()
    net.start()
    try:
        print("*** Preparing hosts (reno, SACK off, offloads off, initcwnd " + str(INITCWND) + ")")
        problems = []
        for host in net.hosts:
            for problem in host_setup.prepare_host(host, initcwnd=INITCWND):
                problems.append(host.name + ": " + problem)
        if len(problems) > 0:
            # A wrong sysctl or route would make every result meaningless
            raise SetupError("host setup FAILED:\n    " + "\n    ".join(problems))
        for switch in net.switches:
            host_setup.disable_switch_offloads(switch)
        warm_up(net, info)

        for scenario_id in scenario_ids:
            scenario = scenarios.get_scenario(scenario_id)
            print(scenario_id + ": " + scenario["name"] + " (" + str(args.runs) + " runs per variant)")
            run_scenario(net, info, scenario_id, args.runs, os.path.abspath(args.out),
                         only_variant=args.variant, controller=args.controller)
    except SetupError as error:
        print()
        print("!" * 70)
        print("ERROR: " + str(error))
        print("Stopped. The failed run was NOT added to mininet_summary.json.")
        print("!" * 70)
        return 2
    finally:
        net.stop()
    print("Results written to " + os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
