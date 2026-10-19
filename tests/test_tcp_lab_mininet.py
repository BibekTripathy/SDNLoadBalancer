"""
Unit tests for the Mininet part of the TCP lab, on canned data (no root,
no Mininet needed).

The files in tests/data/tcp_lab/ are REAL outputs captured from Linux
"reno" with SACK off (in a network namespace with netem, 2 % loss):
  ss_tin_sample.txt, iperf3_tcp_sample.json, iperf3_udp_sample.json,
  nstat_sample.txt, tc_stats_sample.txt
The pcap is built byte by byte below so every number can be checked by hand.
"""

import os
import struct

import pytest

from tcp_lab.mininet import host_setup, pcap_parser, ss_sampler, tc_controller, traffic

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "tcp_lab")


def read_data(name):
    with open(os.path.join(DATA_DIR, name)) as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# ss -tin parser
# ---------------------------------------------------------------------------
def test_ss_parser_reads_real_output():
    samples = ss_sampler.parse_ss_output(read_data("ss_tin_sample.txt"), timestamp=1.5)
    assert len(samples) == 4

    first = samples[0]   # iperf3 control connection, no loss yet -> no ssthresh
    assert first["time"] == 1.5
    assert first["local"] == "127.0.0.1:54692"
    assert first["cc"] == "reno"
    assert first["cwnd"] == 10
    assert first["ssthresh"] is None

    data = samples[1]    # data connection after timeouts
    assert data["peer"] == "127.0.0.1:5201"
    assert data["cwnd"] == 1
    assert data["ssthresh"] == 5
    assert data["rtt_ms"] == 20.044
    assert data["rttvar_ms"] == 7.519
    assert data["rto_ms"] == 1768.0
    assert data["bytes_sent"] == 110117
    assert data["bytes_retrans"] == 66048
    assert data["bytes_acked"] == 38
    assert data["retrans_now"] == 1
    assert data["retrans_total"] == 3
    assert data["lost"] == 2
    assert data["unacked"] == 2
    assert data["delivery_rate_mbps"] == pytest.approx(8.790136)

    # IPv6-mapped address of the server side socket is kept as printed
    assert samples[2]["local"] == "[::ffff:127.0.0.1]:5201"


def test_ss_pick_main_flow_uses_bytes_sent():
    samples = ss_sampler.parse_ss_output(read_data("ss_tin_sample.txt"))
    # The stalled data connection acked fewer bytes (38) than the control
    # connection (185) but SENT far more (110117 vs 184).
    assert ss_sampler.pick_main_flow(samples) == "127.0.0.1:54708"


def test_ss_rate_units_and_addresses():
    assert ss_sampler.parse_rate_mbps("8790136bps") == pytest.approx(8.790136)
    assert ss_sampler.parse_rate_mbps("9.5Mbps") == 9.5
    assert ss_sampler.parse_rate_mbps("120Kbps") == pytest.approx(0.12)
    assert ss_sampler.parse_rate_mbps("1.2Gbps") == pytest.approx(1200.0)
    assert ss_sampler.split_address("[::ffff:10.0.0.1]:5201") == ("10.0.0.1", 5201)
    assert ss_sampler.split_address("10.0.0.11:43210") == ("10.0.0.11", 43210)


def test_ss_parser_older_rate_format():
    text = ("State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "ESTAB 0 0 10.0.0.11:40000 10.0.0.21:5201\n"
            "\t reno rtt:3.5/0.4 cwnd:12 ssthresh:7 delivery_rate 9.5Mbps retrans:0/4\n")
    samples = ss_sampler.parse_ss_output(text)
    assert samples[0]["cwnd"] == 12
    assert samples[0]["ssthresh"] == 7
    assert samples[0]["delivery_rate_mbps"] == 9.5
    assert samples[0]["retrans_total"] == 4


def test_ss_csv_round_trip(tmp_path):
    import csv
    path = os.path.join(str(tmp_path), "ss.csv")
    samples = ss_sampler.parse_ss_output(read_data("ss_tin_sample.txt"), timestamp=0.05)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ss_sampler.SS_COLUMNS)
        writer.writeheader()
        for sample in samples:
            writer.writerow(sample)
    rows = ss_sampler.read_samples_csv(path)
    assert rows[1]["cwnd"] == 1.0
    assert rows[1]["cc"] == "reno"
    assert rows[0]["ssthresh"] is None


# ---------------------------------------------------------------------------
# pcap parser (synthetic, hand-checkable capture)
# ---------------------------------------------------------------------------
SENDER = ("10.0.0.11", 40000)
RECEIVER = ("10.0.0.21", 5201)
SYN = 0x02
ACK = 0x10
PSH_ACK = 0x18
SYN_ACK = 0x12


def ip_bytes(address):
    parts = address.split(".")
    return bytes([int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])])


def make_frame(src, dst, seq, ack, flags, payload_len, window=1000, proto=6):
    """Ethernet + IPv4 + TCP headers only (payload cut off like tcpdump -s 96)."""
    ethernet = b"\x00" * 12 + struct.pack("!H", 0x0800)
    total_len = 20 + 20 + payload_len
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total_len, 0, 0, 64, proto, 0,
                     ip_bytes(src[0]), ip_bytes(dst[0]))
    tcp = struct.pack("!HHIIBBHHH", src[1], dst[1], seq, ack, 5 << 4, flags, window, 0, 0)
    return ethernet + ip + tcp


def make_pcap(frames, order="<"):
    """frames: list of (time, frame bytes) -> classic pcap file bytes."""
    data = struct.pack(order + "IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 96, 1)
    for time_s, frame in frames:
        seconds = int(time_s)
        micros = round((time_s - seconds) * 1e6)
        data = data + struct.pack(order + "IIII", seconds, micros, len(frame), len(frame) + 1000)
        data = data + frame
    return data


def sample_capture():
    """
    ISN of the sender = 1000, 100-byte segments.
    Relative seq 0,100,200,300,400 are sent; 100 is lost after the capture
    point, so the receiver ACKs 100 four times (1 normal + 3 duplicates),
    the sender retransmits 100, and the receiver ACKs 500.
    """
    s, r = SENDER, RECEIVER
    frames = [
        (10.000, make_frame(s, r, 1000, 0, SYN, 0)),
        (10.010, make_frame(r, s, 5000, 1001, SYN_ACK, 0)),
        (10.010, make_frame(s, r, 1001, 5001, ACK, 0)),
        (10.020, make_frame(s, r, 1001, 5001, PSH_ACK, 100)),   # rel 0
        (10.021, make_frame(s, r, 1101, 5001, PSH_ACK, 100)),   # rel 100 (lost later)
        (10.022, make_frame(s, r, 1201, 5001, PSH_ACK, 100)),   # rel 200
        (10.023, make_frame(s, r, 1301, 5001, PSH_ACK, 100)),   # rel 300
        (10.024, make_frame(s, r, 1401, 5001, PSH_ACK, 100)),   # rel 400
        (10.030, make_frame(r, s, 5001, 1101, ACK, 0)),         # ack 100
        (10.031, make_frame(r, s, 5001, 1101, ACK, 0)),         # dup 1
        (10.032, make_frame(r, s, 5001, 1101, ACK, 0)),         # dup 2
        (10.033, make_frame(r, s, 5001, 1101, ACK, 0)),         # dup 3 -> fast retransmit
        (10.034, make_frame(s, r, 1101, 5001, PSH_ACK, 100)),   # retransmission of rel 100
        (10.044, make_frame(r, s, 5001, 1501, ACK, 0)),         # ack 500 (everything)
        # noise: a small second connection (like iperf3's control channel) and UDP
        (10.050, make_frame(("10.0.0.11", 40001), RECEIVER, 7, 1, PSH_ACK, 37)),
        (10.060, make_frame(s, r, 0, 0, 0, 8, proto=17)),
    ]
    return frames


def test_pcap_reader_basic_fields(tmp_path):
    path = os.path.join(str(tmp_path), "sample.pcap")
    with open(path, "wb") as handle:
        handle.write(make_pcap(sample_capture()))
    packets = pcap_parser.read_pcap(path)
    assert len(packets) == 15            # the UDP packet is skipped
    first = packets[0]
    assert first["src_ip"] == "10.0.0.11"
    assert first["dst_port"] == 5201
    assert first["flags"] == SYN
    assert first["time"] == pytest.approx(10.0)
    # payload length comes from the IP header although the payload was not captured
    assert packets[3]["len"] == 100


def test_pcap_big_endian_file_gives_same_packets():
    little = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture(), "<"))
    big = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture(), ">"))
    assert len(little) == len(big)
    assert little[4]["seq"] == big[4]["seq"]


def test_pcap_analysis_finds_retransmission_and_dupacks():
    packets = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture()))
    flow = pcap_parser.find_main_flow(packets, "10.0.0.11")
    assert flow == ("10.0.0.11", 40000, "10.0.0.21", 5201)   # not the 37-byte connection

    rows, summary = pcap_parser.analyse_flow(packets, flow)
    assert summary["data_packets"] == 6        # 5 originals + 1 retransmission
    assert summary["data_bytes"] == 600
    assert summary["unique_bytes"] == 500
    assert summary["retransmissions"] == 1
    assert summary["retransmitted_bytes"] == 100
    assert summary["dupacks"] == 3
    assert summary["longest_dupack_run"] == 3

    data_rows = [row for row in rows if row["direction"] == "DATA"]
    seqs = [row["seq"] for row in data_rows]
    assert seqs == [0, 100, 200, 300, 400, 100]
    assert data_rows[-1]["retransmission"] == 1

    ack_rows = [row for row in rows if row["direction"] == "ACK"]
    dup_counts = [row["dupack_count"] for row in ack_rows]
    # SYN-ACK, ack 100, dup 1, dup 2, dup 3, ack 500
    assert dup_counts == [0, 0, 1, 2, 3, 0]
    assert ack_rows[-1]["ack"] == 500


def test_pcap_window_change_is_not_a_dupack():
    s, r = SENDER, RECEIVER
    frames = [
        (1.0, make_frame(s, r, 1000, 0, SYN, 0)),
        (1.1, make_frame(s, r, 1001, 1, PSH_ACK, 100)),
        (1.2, make_frame(s, r, 1101, 1, PSH_ACK, 100)),
        (1.3, make_frame(r, s, 1, 1101, ACK, 0, window=1000)),
        (1.4, make_frame(r, s, 1, 1101, ACK, 0, window=2000)),   # window update, not a dup
        (1.5, make_frame(r, s, 1, 1101, ACK, 0, window=2000)),   # real dup
    ]
    packets = pcap_parser.parse_pcap_bytes(make_pcap(frames))
    _rows, summary = pcap_parser.analyse_flow(packets, pcap_parser.find_main_flow(packets, s[0]))
    assert summary["dupacks"] == 1


def test_pcap_rejects_non_pcap():
    with pytest.raises(ValueError):
        pcap_parser.parse_pcap_bytes(b"\x0a\x0d\x0d\x0a" + b"\x00" * 40)   # pcapng


def test_pcap_sequence_csv(tmp_path):
    packets = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture()))
    rows, _summary = pcap_parser.analyse_flow(packets, pcap_parser.find_main_flow(packets, "10.0.0.11"))
    path = os.path.join(str(tmp_path), "seq.csv")
    pcap_parser.write_sequence_csv(rows, path)
    with open(path) as handle:
        lines = handle.read().splitlines()
    assert lines[0] == ",".join(pcap_parser.SEQUENCE_COLUMNS)
    assert len(lines) == len(rows) + 1


# ---------------------------------------------------------------------------
# tc command builders
# ---------------------------------------------------------------------------
def test_tc_default_conditions():
    commands = tc_controller.build_tc_commands("sw1-eth1", tc_controller.default_conditions())
    assert commands == [
        "tc qdisc replace dev sw1-eth1 root handle 1: netem limit 10000 delay 10ms",
        # burst = max(10 x 1514, 10 ms at 10 Mbit/s = 12500) = 15140; limit = 100 x 1514
        "tc qdisc replace dev sw1-eth1 parent 1:1 handle 10: tbf rate 10mbit burst 15140 limit 151400",
    ]


def test_tc_random_loss_jitter_and_queue():
    conditions = tc_controller.merged_conditions(
        tc_controller.default_conditions(),
        {"delay_ms": 25, "jitter_ms": 2, "loss_pct": 1, "queue_packets": 50, "rate_mbps": 100})
    netem, tbf = tc_controller.build_tc_commands("sw1-eth1", conditions)
    assert netem.endswith("delay 25ms 2ms loss random 1%")
    # 10 ms at 100 Mbit/s = 125000 bytes; 50 packets = 75700 bytes
    assert tbf.endswith("tbf rate 100mbit burst 125000 limit 75700")


def test_tc_burst_loss_uses_gilbert_elliott():
    conditions = tc_controller.merged_conditions(
        tc_controller.default_conditions(),
        {"loss_pct": 5, "burst_loss": {"p_pct": 1, "r_pct": 25}})
    netem = tc_controller.build_netem_command("sw1-eth1", conditions)
    # burst loss wins over the random loss setting
    assert netem.endswith("delay 10ms loss gemodel 1% 25%")
    assert "random" not in netem


def test_tc_no_rate_limit_means_netem_only():
    conditions = tc_controller.merged_conditions(tc_controller.default_conditions(),
                                                 {"rate_mbps": None, "delay_ms": 2.5})
    commands = tc_controller.build_tc_commands("sw2-eth1", conditions)
    assert commands == ["tc qdisc replace dev sw2-eth1 root handle 1: netem limit 10000 delay 2.5ms"]


def test_tc_clear_and_stats_commands():
    assert tc_controller.build_clear_command("sw1-eth1") == "tc qdisc del dev sw1-eth1 root"
    assert tc_controller.build_stats_command("sw1-eth1") == "tc -s qdisc show dev sw1-eth1"


def test_tc_stats_parser_on_real_output():
    qdiscs = tc_controller.parse_tc_stats(read_data("tc_stats_sample.txt"))
    assert len(qdiscs) == 2
    netem, tbf = qdiscs
    assert netem["kind"] == "netem"
    assert netem["sent_packets"] == 2697
    assert netem["dropped"] == 52          # the random 2 % loss
    assert tbf["kind"] == "tbf"
    assert tbf["dropped"] == 0
    assert tbf["overlimits"] == 1551


class FakeNode:
    """Stands in for a Mininet node: remembers commands, returns canned output."""

    def __init__(self, reply=""):
        self.commands = []
        self.reply = reply

    def cmd(self, command):
        self.commands.append(command)
        return self.reply


def test_tc_apply_and_timeline():
    node = FakeNode()
    log = []
    step = tc_controller.merged_conditions(tc_controller.default_conditions(), {"rate_mbps": 2})
    import time
    tc_controller.run_timeline(node, "sw1-eth1", [{"time": 0.0, "conditions": step}],
                               time.time(), log)
    assert node.commands[1].startswith("tc qdisc replace dev sw1-eth1 parent 1:1 handle 10: tbf rate 2mbit")
    assert len(log) == 1
    assert log[0]["conditions"]["rate_mbps"] == 2


def test_tc_apply_raises_on_error():
    node = FakeNode(reply="Error: Exclusivity flag on, cannot modify.")
    with pytest.raises(RuntimeError):
        tc_controller.apply_conditions(node, "sw1-eth1", tc_controller.default_conditions())


# ---------------------------------------------------------------------------
# Host setup
# ---------------------------------------------------------------------------
def test_host_setup_commands():
    commands = host_setup.build_sysctl_commands()
    assert "sysctl -w net.ipv4.tcp_congestion_control=reno" in commands
    assert "sysctl -w net.ipv4.tcp_sack=0" in commands
    assert "sysctl -w net.ipv4.tcp_no_metrics_save=1" in commands
    assert host_setup.build_offload_commands("c1-eth0") == [
        "ethtool -K c1-eth0 tso off gso off gro off"]


def test_initcwnd_rewrites_every_route_once():
    routes = [
        "10.0.0.0/24 dev c1-eth0 proto kernel scope link src 10.0.0.11",
        "default via 10.0.0.100 dev client-eth0 initcwnd 10",
        "",
    ]
    assert host_setup.build_initcwnd_commands(routes, 1) == [
        "ip route change 10.0.0.0/24 dev c1-eth0 proto kernel scope link src 10.0.0.11 initcwnd 1",
        "ip route change default via 10.0.0.100 dev client-eth0 initcwnd 1",
    ]


def test_sysctl_check():
    good = ""
    for name, value, _why in host_setup.SYSCTL_SETTINGS:
        good = good + name + " = " + value + "\n"
    assert host_setup.check_settings(host_setup.parse_sysctl_output(good)) == []
    bad = good.replace("net.ipv4.tcp_sack = 0", "net.ipv4.tcp_sack = 1")
    problems = host_setup.check_settings(host_setup.parse_sysctl_output(bad))
    assert problems == ["net.ipv4.tcp_sack = 1 (wanted 0)"]


# ---------------------------------------------------------------------------
# iperf3 / nstat / tcpdump
# ---------------------------------------------------------------------------
def test_iperf3_command_builders():
    assert traffic.iperf3_tcp_client_cmd("10.0.0.21", 20) == [
        "iperf3", "-c", "10.0.0.21", "-p", "5201", "-t", "20", "-C", "reno", "-J"]
    assert traffic.iperf3_udp_client_cmd("10.0.0.22", 2, 10) == [
        "iperf3", "-c", "10.0.0.22", "-p", "5201", "-u", "-b", "2M", "-l", "1400", "-t", "10", "-J"]
    assert traffic.iperf3_server_cmd() == ["iperf3", "-s", "-p", "5201", "-1"]
    assert traffic.tcpdump_cmd("c1-eth0", "/tmp/x.pcap") == [
        "tcpdump", "-i", "c1-eth0", "-n", "-s", "96", "-U", "-w", "/tmp/x.pcap", "tcp"]


def test_iperf3_tcp_parser_on_real_report():
    result = traffic.parse_iperf3_tcp(read_data("iperf3_tcp_sample.json"))
    assert result["congestion_control"] == "reno"
    assert result["retransmits"] == 50
    assert result["sent_bytes"] == 2752512
    assert result["received_bytes"] == 2490368
    assert result["max_snd_cwnd_bytes"] == 21720
    assert result["goodput_mbps"] == pytest.approx(3.968, abs=0.01)
    assert result["mean_rtt_ms"] == pytest.approx(23.998, abs=0.01)


def test_iperf3_udp_parser_on_real_report():
    result = traffic.parse_iperf3_udp(read_data("iperf3_udp_sample.json"))
    assert result["packets"] == 358
    assert result["lost_packets"] == 16
    assert result["sent_mbps"] > result["received_mbps"]


def test_iperf3_error_is_raised():
    with pytest.raises(RuntimeError):
        traffic.parse_iperf3_tcp('{"start": {}, "end": {}, "error": "unable to connect to server"}')


def test_nstat_parser_and_diff():
    after = traffic.parse_nstat(read_data("nstat_sample.txt"))
    # These agree with iperf3 (50 retransmits) for the same real run
    assert after["TcpRetransSegs"] == 50
    assert after["TcpExtTCPRenoRecovery"] == 22
    assert after["TcpExtTCPFastRetrans"] == 45
    assert after["TcpExtTCPTimeouts"] == 3
    before = {}
    for name in after:
        before[name] = 0
    before["TcpRetransSegs"] = 10
    diff = traffic.diff_counters(before, after)
    assert diff["TcpRetransSegs"] == 40
    assert diff["TcpExtTCPTimeouts"] == 3


# ---------------------------------------------------------------------------
# Topology (only where the mininet Python package is installed)
# ---------------------------------------------------------------------------
def test_dumbbell_topology_wiring():
    pytest.importorskip("mininet")
    from tcp_lab.mininet import dumbbell_topo

    topo = dumbbell_topo.DumbbellTopo(bw_mbps=10, delay_ms=10, queue_packets=100)
    assert sorted(topo.hosts()) == ["c1", "c2", "c3", "sv1", "sv2"]
    bottleneck = None
    for a, b, info in topo.links(withInfo=True):
        if a.startswith("sw") and b.startswith("sw"):
            bottleneck = info
    assert bottleneck["port1"] == 1 and bottleneck["port2"] == 1
    assert bottleneck["bw"] == 10
    assert bottleneck["max_queue_size"] == 100


# ---------------------------------------------------------------------------
# Phase 4 additions: several flows per client, spurious resends at the receiver
# ---------------------------------------------------------------------------
def test_find_flow_to_picks_the_data_connection_of_one_port():
    packets = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture()))
    # Same server port as the 37-byte "control" connection: still the big one
    assert pcap_parser.find_flow_to(packets, "10.0.0.11", "10.0.0.21", 5201) == (
        "10.0.0.11", 40000, "10.0.0.21", 5201)
    assert pcap_parser.find_flow_to(packets, "10.0.0.11", "10.0.0.21", 5202) is None


def test_needed_retransmission_is_not_spurious():
    # In sample_capture the resent segment (rel 100) filled a real hole
    packets = pcap_parser.parse_pcap_bytes(make_pcap(sample_capture()))
    flow = pcap_parser.find_main_flow(packets, "10.0.0.11")
    result = pcap_parser.count_spurious_at_receiver(packets, flow)
    assert result["arrived_data_packets"] == 6
    assert result["spurious_retransmissions"] == 0


def test_spurious_retransmission_seen_at_receiver():
    """
    Receiver-side capture: rel 0 and 100 arrive and are ACKed (ack 200),
    but the sender's timer fires anyway and it resends rel 0 and rel 100.
    Both copies end at or below the ACK already sent -> 2 spurious.
    Then rel 200 (new data) arrives: not spurious.
    """
    s, r = SENDER, RECEIVER
    frames = [
        (1.00, make_frame(s, r, 1000, 0, SYN, 0)),
        (1.01, make_frame(r, s, 5000, 1001, SYN_ACK, 0)),
        (1.02, make_frame(s, r, 1001, 5001, PSH_ACK, 100)),   # rel 0
        (1.03, make_frame(s, r, 1101, 5001, PSH_ACK, 100)),   # rel 100
        (1.04, make_frame(r, s, 5001, 1201, ACK, 0)),         # ack 200 (the ACK gets lost later)
        (2.00, make_frame(s, r, 1001, 5001, PSH_ACK, 100)),   # timeout resend of rel 0
        (2.01, make_frame(s, r, 1101, 5001, PSH_ACK, 100)),   # and rel 100
        (2.02, make_frame(s, r, 1201, 5001, PSH_ACK, 100)),   # rel 200, new
    ]
    packets = pcap_parser.parse_pcap_bytes(make_pcap(frames))
    result = pcap_parser.count_spurious_at_receiver(packets, (s[0], s[1], r[0], r[1]))
    assert result["arrived_data_packets"] == 5
    assert result["spurious_retransmissions"] == 2
    assert result["spurious_bytes"] == 200


def test_ss_pick_flow_to_one_server_port():
    samples = ss_sampler.parse_ss_output(read_data("ss_tin_sample.txt"))
    # Two client sockets go to 127.0.0.1:5201; the data one sent the most
    assert ss_sampler.pick_flow_to(samples, "127.0.0.1", 5201) == "127.0.0.1:54708"
    assert ss_sampler.pick_flow_to(samples, "127.0.0.1", 5999) is None
    assert len(ss_sampler.samples_of(samples, "127.0.0.1:54708")) == 1


def test_tc_netem_seed():
    conditions = tc_controller.merged_conditions(tc_controller.default_conditions(),
                                                 {"loss_pct": 1, "seed": 3})
    command = tc_controller.build_netem_command("sw1-eth1", conditions)
    assert command.endswith("loss random 1% seed 3")
    # dicts from before "seed" existed still work
    old = tc_controller.default_conditions()
    del old["seed"]
    assert "seed" not in tc_controller.build_netem_command("sw1-eth1", old)


class FakeRouteHost:
    """A host with one route; `ip route change` really changes it."""

    def __init__(self, colour):
        self.colour = colour
        self.route = "10.0.0.0/24 dev c1-eth0 proto kernel scope link src 10.0.0.11"

    def intfNames(self):
        return ["c1-eth0"]

    def cmd(self, command):
        if command.startswith("ip route show"):
            if self.colour and "| cat" not in command:
                # what iproute2 prints on a terminal (Mininet's pty)
                return "\x1b[1;35m10.0.0.0/24 \x1b[0mdev \x1b[1;36mc1-eth0 \x1b[0mproto kernel"
            return self.route
        if command.startswith("ip route change "):
            new_route = command[len("ip route change "):]
            if "\x1b" not in new_route:          # ip rejects the escape codes
                self.route = new_route
            return ""
        if command.startswith("sysctl ") and not command.startswith("sysctl -w"):
            text = ""
            for name, value, _why in host_setup.SYSCTL_SETTINGS:
                text = text + name + " = " + value + "\n"
            return text
        return ""


def test_prepare_host_sets_initcwnd_even_with_coloured_ip_output():
    host = FakeRouteHost(colour=True)
    assert host_setup.prepare_host(host, initcwnd=1) == []
    assert host.route.endswith("initcwnd 1")


def test_check_initcwnd_reports_missing_routes():
    lines = ["10.0.0.0/24 dev c1-eth0 initcwnd 1", "default via 10.0.0.1 dev c1-eth0", ""]
    assert host_setup.check_initcwnd(lines, 1) == [
        "route without initcwnd 1: default via 10.0.0.1 dev c1-eth0"]


# ---------------------------------------------------------------------------
# Initial cwnd: ignore the handshake, then cwnd - (delivered - 1)
# ss_initcwnd_1.csv / ss_initcwnd_default.csv are REAL samples (10 ms apart)
# of an iperf3 reno connection with initcwnd 1 and with Linux's default 10.
# ---------------------------------------------------------------------------
def test_ss_parser_keeps_state_and_delivered():
    text = ("State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
            "SYN-SENT 0 1 10.0.0.11:45442 10.0.0.21:5201\n"
            "\t reno rto:1000 mss:524 cwnd:10 segs_out:1 lastsnd:4\n"
            "ESTAB 0 0 10.0.0.11:45430 10.0.0.21:5201\n"
            "\t reno rto:241 rtt:40.5/20.2 mss:1448 cwnd:2 bytes_sent:37 bytes_acked:38 delivered:2\n")
    samples = ss_sampler.parse_ss_output(text)
    assert samples[0]["state"] == "SYN-SENT"
    assert samples[0]["cwnd"] == 10
    assert samples[0]["rtt_ms"] is None
    assert samples[1]["state"] == "ESTAB"
    assert samples[1]["delivered"] == 2


def initcwnd_samples(name):
    samples = ss_sampler.read_samples_csv(os.path.join(DATA_DIR, name))
    local = ss_sampler.pick_flow_to(samples, "10.0.0.21", 5201)
    return ss_sampler.samples_of(samples, local)


def test_handshake_samples_are_skipped():
    samples = initcwnd_samples("ss_initcwnd_1.csv")
    assert samples[0]["state"] == "SYN-SENT"
    assert samples[0]["cwnd"] == 10          # what the old "first cwnd" reported
    first = ss_sampler.first_established_sample(samples)
    assert first["state"] == "ESTAB"
    assert first["cwnd"] == 1


def test_initial_cwnd_estimate_on_real_samples():
    assert ss_sampler.estimate_initial_cwnd(initcwnd_samples("ss_initcwnd_1.csv")) == 1
    assert ss_sampler.estimate_initial_cwnd(initcwnd_samples("ss_initcwnd_default.csv")) == 10


def test_initial_cwnd_when_sampled_late():
    # Like the S3 loss_1pct run: the first established sample came after
    # the 37-byte cookie was ACKed, so cwnd had already grown to 2.
    samples = [
        {"state": "SYN-SENT", "cwnd": 10, "ssthresh": None, "rtt_ms": None, "delivered": None},
        {"state": "ESTAB", "cwnd": 2, "ssthresh": None, "rtt_ms": 40.1, "delivered": 2},
    ]
    assert ss_sampler.estimate_initial_cwnd(samples) == 1


def test_initial_cwnd_unknown_cases():
    # loss before the first sample: slow start is over, the rule does not hold
    after_loss = [{"state": "ESTAB", "cwnd": 2, "ssthresh": 2, "rtt_ms": 40.0, "delivered": 9}]
    assert ss_sampler.estimate_initial_cwnd(after_loss) is None
    # CSV from before the state/delivered columns: no "delivered" -> unknown
    old = [{"cwnd": 10, "ssthresh": None, "rtt_ms": None},
           {"cwnd": 2, "ssthresh": None, "rtt_ms": 40.0}]
    assert ss_sampler.first_established_sample(old)["cwnd"] == 2
    assert ss_sampler.estimate_initial_cwnd(old) is None
    assert ss_sampler.estimate_initial_cwnd([]) is None
