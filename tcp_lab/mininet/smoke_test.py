"""
One short end-to-end Mininet experiment that exercises every Phase 3 part:
topology, host preparation, tc conditions changed at runtime, the ss
sampler, tcpdump + pcap parser, and the iperf3 / nstat parsers.

    sudo python3 -m tcp_lab.mininet.smoke_test                    # dumbbell, OVS standalone
    sudo python3 -m tcp_lab.mininet.smoke_test --controller ryu   # dumbbell, Ryu on :6653
    sudo python3 -m tcp_lab.mininet.smoke_test --target vip       # client -> VIP through the LB
                                                                  # (Ryu LB must be running,
                                                                  #  LB Mininet must NOT be)

What it does (dumbbell): one Linux reno flow c1 -> sv1 for 20 s over a
10 Mbit/s bottleneck with 10 ms one-way delay; at half time the bandwidth
steps down to 3 Mbit/s. Results go to results/mininet_smoke/<target>/.
"""

import argparse
import json
import os
import shutil
import sys
import threading
import time

from tcp_lab.mininet import (
    cleanup,
    host_setup,
    pcap_parser,
    ss_sampler,
    tc_controller,
    traffic,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQUIRED_TOOLS = ["iperf3", "tcpdump", "ss", "nstat", "ethtool", "tc", "mn"]
BULK_PORT = 5001


def check_environment():
    problems = []
    if os.geteuid() != 0:
        problems.append("must run as root (sudo python3 -m tcp_lab.mininet.smoke_test)")
    for tool in REQUIRED_TOOLS:
        if shutil.which(tool) is None:
            problems.append("missing tool: " + tool)
    return problems


def popen_in(node, command, out_path):
    """Start a background process on a Mininet node, output to a file.
    The file stays open while the process runs; the caller closes it."""
    handle = open(out_path, "w")  # noqa: SIM115
    process = node.popen(command, stdout=handle, stderr=handle, cwd=PROJECT_ROOT)
    return process, handle


def apply_initial_conditions(net, info, forward, reverse):
    for switch_name, interface in info["forward_interfaces"]:
        tc_controller.apply_conditions(net.get(switch_name), interface, forward)
    for switch_name, interface in info["reverse_interfaces"]:
        tc_controller.apply_conditions(net.get(switch_name), interface, reverse)


def run_bandwidth_step(net, info, timeline, start_time, change_log):
    """Apply the same timeline on every forward interface (one thread each)."""
    threads = []
    for switch_name, interface in info["forward_interfaces"]:
        worker = threading.Thread(target=tc_controller.run_timeline,
                                  args=(net.get(switch_name), interface, timeline,
                                        start_time, change_log))
        worker.start()
        threads.append(worker)
    return threads


def main():
    parser = argparse.ArgumentParser(description="TCP lab Mininet smoke test")
    parser.add_argument("--target", choices=["dumbbell", "vip"], default="dumbbell")
    parser.add_argument("--controller", choices=["standalone", "ryu"], default="standalone")
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--out", default=os.path.join(PROJECT_ROOT, "results", "mininet_smoke"))
    args = parser.parse_args()

    problems = check_environment()
    if len(problems) > 0:
        for problem in problems:
            print("ERROR: " + problem)
        return 1

    # Imported here so the error above is shown even where Mininet is missing
    from mininet.log import setLogLevel

    from tcp_lab.mininet import dumbbell_topo

    setLogLevel("warning")
    # Remove leftovers of an earlier run (our own cleanup, not `mn -c`:
    # see cleanup.py for why)
    cleanup.cleanup_lab(args.target, verbose=False)

    out_dir = os.path.abspath(os.path.join(args.out, args.target))
    os.makedirs(out_dir, exist_ok=True)

    if args.target == "dumbbell":
        net = dumbbell_topo.build_dumbbell_net(controller=args.controller)
        info = dumbbell_topo.dumbbell_info()
        net.start()
    else:
        net = dumbbell_topo.build_vip_net()
        info = dumbbell_topo.vip_info()
        dumbbell_topo.start_vip_net(net)

    processes = []
    files = []
    summary = {"source": "mininet", "algorithm": "linux_reno", "target": args.target}
    try:
        # 1) Make Linux TCP textbook-like on every host; offloads off on switches
        print("*** Preparing hosts (reno, SACK off, offloads off, initcwnd 1)")
        for host in net.hosts:
            host_problems = host_setup.prepare_host(host, initcwnd=1)
            for problem in host_problems:
                print("  WARNING " + host.name + ": " + problem)
        for switch in net.switches:
            host_setup.disable_switch_offloads(switch)

        # 2) Bottleneck: 10 Mbit/s, 10 ms each way (base RTT about 20 ms), 100 packet queue
        forward = tc_controller.default_conditions()
        reverse = tc_controller.merged_conditions(forward, {"rate_mbps": None})
        apply_initial_conditions(net, info, forward, reverse)

        client = net.get(info["clients"][0]["name"])
        if args.target == "dumbbell":
            server = net.get(info["servers"][0]["name"])
            target_ip = info["servers"][0]["ip"]
        else:
            target_ip = info["target_ip"]

        print("*** Ping " + target_ip)
        print(client.cmd("ping -c 3 -W 1 " + target_ip).strip().splitlines()[-1])

        # 3) Receivers
        if args.target == "dumbbell":
            process, handle = popen_in(server, traffic.iperf3_server_cmd(),
                                       os.path.join(out_dir, "iperf3_server.log"))
            processes.append(process)
            files.append(handle)
        else:
            for item in info["servers"]:
                process, handle = popen_in(
                    net.get(item["name"]),
                    [sys.executable, "-m", "tcp_lab.mininet.bulk_tcp", "recv",
                     "--port", str(BULK_PORT)],
                    os.path.join(out_dir, "receiver_" + item["name"] + ".log"))
                processes.append(process)
                files.append(handle)
        time.sleep(1.0)

        # 4) Measurement: tcpdump on the sender, ss sampler, nstat before
        sender_interface = client.intfNames()[0]
        sender_pcap = os.path.join(out_dir, "sender.pcap")
        process, handle = popen_in(client, traffic.tcpdump_cmd(sender_interface, sender_pcap),
                                   os.path.join(out_dir, "tcpdump.log"))
        processes.append(process)
        files.append(handle)
        ss_csv = os.path.join(out_dir, "mininet_linux_reno_ss.csv")
        sampler, handle = popen_in(
            client,
            [sys.executable, "-m", "tcp_lab.mininet.ss_sampler", "--dst", target_ip,
             "--duration", str(args.duration + 2), "--out", ss_csv],
            os.path.join(out_dir, "ss_sampler.log"))
        files.append(handle)
        nstat_before = traffic.parse_nstat(client.cmd(traffic.NSTAT_CMD))
        time.sleep(0.5)

        # 5) Traffic + a bandwidth step 10 -> 3 Mbit/s at half time
        print("*** Running TCP for " + str(args.duration) + " s (bandwidth 10 -> 3 Mbit/s at "
              + str(args.duration / 2) + " s)")
        start_time = time.time()
        if args.target == "dumbbell":
            client_cmd = traffic.iperf3_tcp_client_cmd(target_ip, args.duration)
        else:
            client_cmd = [sys.executable, "-m", "tcp_lab.mininet.bulk_tcp", "send",
                          "--host", target_ip, "--port", str(BULK_PORT),
                          "--time", str(args.duration), "--cc", "reno"]
        sender = client.popen(client_cmd, cwd=PROJECT_ROOT)
        change_log = []
        step = tc_controller.merged_conditions(forward, {"rate_mbps": 3.0})
        timeline = [{"time": args.duration / 2.0, "conditions": step}]
        tc_threads = run_bandwidth_step(net, info, timeline, start_time, change_log)
        client_output, _errors = sender.communicate()
        for worker in tc_threads:
            worker.join()

        nstat_after = traffic.parse_nstat(client.cmd(traffic.NSTAT_CMD))
        sampler.wait()
        time.sleep(0.5)

        # 6) UDP through the VIP as well (shows UDP is load balanced too)
        if args.target == "vip":
            print("*** Sending 3 s of UDP at 2 Mbit/s to the VIP")
            udp_out = client.cmd(" ".join([
                sys.executable, "-m", "tcp_lab.mininet.bulk_tcp", "send", "--host", target_ip,
                "--port", str(BULK_PORT), "--time", "3", "--udp", "--rate", "2"]))
            summary["udp_sender"] = json.loads(udp_out.strip().splitlines()[-1])
            time.sleep(1.5)   # receivers print their UDP totals after 1 s of silence

        # 7) Stop capture, collect tc statistics
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait()
        tc_stats = {}
        for switch_name, interface in info["forward_interfaces"]:
            tc_stats[interface] = tc_controller.parse_tc_stats(
                net.get(switch_name).cmd(tc_controller.build_stats_command(interface)))

        # 8) Parse everything
        text = client_output.decode() if isinstance(client_output, bytes) else client_output
        if args.target == "dumbbell":
            summary["iperf3"] = traffic.parse_iperf3_tcp(text)
        else:
            summary["bulk_sender"] = json.loads(text.strip().splitlines()[-1])
        summary["nstat"] = traffic.diff_counters(nstat_before, nstat_after)
        summary["tc_changes"] = change_log
        summary["tc_stats"] = tc_stats

        packets = pcap_parser.read_pcap(sender_pcap)
        flow = pcap_parser.find_main_flow(packets, info["clients"][0]["ip"])
        if flow is not None:
            rows, pcap_summary = pcap_parser.analyse_flow(packets, flow)
            pcap_parser.write_sequence_csv(rows, os.path.join(out_dir, "mininet_linux_reno_seq.csv"))
            summary["pcap"] = pcap_summary

        samples = ss_sampler.read_samples_csv(ss_csv)
        main_local = ss_sampler.pick_main_flow(samples)
        flow_samples = []
        for sample in samples:
            if sample["local"] == main_local:
                flow_samples.append(sample)
        summary["ss_samples"] = len(flow_samples)
        # The cwnd the connection started with (1 if initcwnd 1 really applied)
        summary["initial_cwnd"] = ss_sampler.estimate_initial_cwnd(flow_samples)
        if len(flow_samples) > 0:
            last = flow_samples[-1]
            summary["ss_last"] = {"cc": last["cc"], "cwnd": last["cwnd"],
                                  "ssthresh": last["ssthresh"], "rtt_ms": last["rtt_ms"],
                                  "retrans_total": last["retrans_total"]}
    finally:
        for handle in files:
            handle.close()
        net.stop()

    with open(os.path.join(out_dir, "summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    all_passed = print_checks(summary)
    print("Files in " + out_dir)
    if not all_passed:
        print("SMOKE TEST FAILED (see the FAIL lines above)")
        return 1
    return 0


def print_checks(summary):
    """Things that should be true if everything works; printed as PASS/FAIL."""
    print("\n*** Checks")
    checks = []
    ss_last = summary.get("ss_last", {})
    checks.append(("ss sampler saw the flow", summary.get("ss_samples", 0) > 20))
    checks.append(("congestion control is reno", ss_last.get("cc") == "reno"))
    checks.append(("connection started with cwnd 1 (initcwnd applied), got "
                   + str(summary.get("initial_cwnd")), summary.get("initial_cwnd") == 1))
    checks.append(("pcap has data packets", summary.get("pcap", {}).get("data_packets", 0) > 0))
    checks.append(("bandwidth step was applied", len(summary.get("tc_changes", [])) > 0))
    retrans = []
    if "iperf3" in summary:
        retrans.append(("iperf3", summary["iperf3"]["retransmits"]))
    retrans.append(("nstat", summary["nstat"].get("TcpRetransSegs")))
    retrans.append(("ss", ss_last.get("retrans_total")))
    retrans.append(("pcap", summary.get("pcap", {}).get("retransmissions")))
    all_passed = True
    for name, ok in checks:
        print("  " + ("PASS" if ok else "FAIL") + "  " + name)
        if not ok:
            all_passed = False
    print("  retransmissions by source (should be equal or very close): " + str(retrans))
    return all_passed


if __name__ == "__main__":
    sys.exit(main())
