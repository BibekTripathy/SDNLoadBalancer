"""
Traffic and measurement commands: iperf3, tcpdump, nstat.

Command builders return argument lists (for host.popen) so they can be
unit tested. The parsers turn tool output into plain dicts.
"""

import json

IPERF3_PORT = 5201


# ---------------------------------------------------------------------------
# iperf3
# ---------------------------------------------------------------------------
def iperf3_server_cmd(port=IPERF3_PORT):
    # -1: serve one test and exit, so every experiment starts fresh
    return ["iperf3", "-s", "-p", str(port), "-1"]


def iperf3_tcp_client_cmd(server_ip, duration, port=IPERF3_PORT, cc="reno"):
    # -C reno: congestion control for this socket; -J: JSON report on stdout
    return ["iperf3", "-c", server_ip, "-p", str(port), "-t", str(duration),
            "-C", cc, "-J"]


def iperf3_udp_client_cmd(server_ip, rate_mbps, duration, port=IPERF3_PORT,
                          packet_bytes=1400):
    # UDP background load: constant bit rate, no congestion control at all
    return ["iperf3", "-c", server_ip, "-p", str(port), "-u",
            "-b", str(rate_mbps) + "M", "-l", str(packet_bytes),
            "-t", str(duration), "-J"]


def parse_iperf3_tcp(text):
    """Pick the useful numbers out of an `iperf3 -J` TCP report."""
    report = json.loads(text)
    if "error" in report:
        raise RuntimeError("iperf3 error: " + report["error"])
    end = report["end"]
    sent = end["sum_sent"]
    received = end["sum_received"]
    result = {
        "sent_bytes": sent["bytes"],
        "received_bytes": received["bytes"],
        "duration_s": received["seconds"],
        "sender_mbps": sent["bits_per_second"] / 1e6,
        # bytes the server application actually read = goodput
        "goodput_mbps": received["bits_per_second"] / 1e6,
        "retransmits": sent.get("retransmits"),
        "congestion_control": end.get("sender_tcp_congestion"),
        "max_snd_cwnd_bytes": None,
        "mean_rtt_ms": None,
    }
    streams = end.get("streams", [])
    if len(streams) > 0 and "sender" in streams[0]:
        stream = streams[0]["sender"]
        if "max_snd_cwnd" in stream:
            result["max_snd_cwnd_bytes"] = stream["max_snd_cwnd"]
        if "mean_rtt" in stream:
            result["mean_rtt_ms"] = stream["mean_rtt"] / 1000.0   # iperf3 reports microseconds
    return result


def parse_iperf3_udp(text):
    report = json.loads(text)
    if "error" in report:
        raise RuntimeError("iperf3 error: " + report["error"])
    end = report["end"]
    sent = end.get("sum_sent", end["sum"])
    # Newer iperf3 versions report the receiver side separately; older ones only "sum"
    received = end.get("sum_received", end["sum"])
    return {
        "sent_mbps": sent["bits_per_second"] / 1e6,
        "received_mbps": received["bits_per_second"] / 1e6,
        "lost_packets": received.get("lost_packets"),
        "packets": received.get("packets"),
        "lost_percent": received.get("lost_percent"),
        "jitter_ms": received.get("jitter_ms"),
    }


# ---------------------------------------------------------------------------
# tcpdump
# ---------------------------------------------------------------------------
def tcpdump_cmd(interface, pcap_path, snaplen=96):
    """
    Capture only headers (96 bytes is enough for Ethernet + IP + TCP options).
    -U writes each packet immediately, so stopping tcpdump loses nothing.
    """
    return ["tcpdump", "-i", interface, "-n", "-s", str(snaplen), "-U",
            "-w", pcap_path, "tcp"]


# ---------------------------------------------------------------------------
# nstat - kernel TCP counters of one host (one network namespace)
# ---------------------------------------------------------------------------
NSTAT_CMD = "nstat -asz"   # absolute values, do not touch nstat's history file, show zeros

# Counters we report, with the meaning used in the README
NSTAT_COUNTERS = [
    "TcpOutSegs",                  # segments sent
    "TcpRetransSegs",              # segments retransmitted (any reason)
    "TcpExtTCPTimeouts",           # retransmission timeouts (RTO fired)
    "TcpExtTCPRenoRecovery",       # times Reno/NewReno fast recovery was entered (no SACK)
    "TcpExtTCPRenoRecoveryFail",   # fast recoveries that still ended in a timeout
    "TcpExtTCPFastRetrans",        # fast retransmissions
    "TcpExtTCPSlowStartRetrans",   # retransmissions sent in slow start after a timeout
    "TcpExtTCPLostRetransmit",     # retransmissions that were lost again
]


def parse_nstat(text):
    """'TcpRetransSegs   4   0.0' lines -> {'TcpRetransSegs': 4}"""
    counters = {}
    for line in text.splitlines():
        words = line.split()
        if len(words) < 2 or line.startswith("#"):
            continue
        try:
            counters[words[0]] = int(words[1])
        except ValueError:
            continue
    return counters


def diff_counters(before, after):
    """How much each interesting counter grew during the experiment."""
    result = {}
    for name in NSTAT_COUNTERS:
        if name in before and name in after:
            result[name] = after[name] - before[name]
        else:
            result[name] = None
    return result
