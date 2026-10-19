"""
Read a tcpdump pcap file and build a TCP time-sequence table.

No tshark or scapy needed: the pcap format and the Ethernet / IPv4 / TCP
headers are simple fixed layouts, read here with the `struct` module.

For one TCP connection (the data sender -> receiver direction) we write,
per packet:
    DATA rows: time, relative seq, payload length, retransmission flag
    ACK rows:  time, relative ack, duplicate-ACK flag, dup ACK count

Rules (written so they can be checked by hand):
  - Relative numbers: seq/ack minus the first sequence number of the
    connection, so the first data byte is 0 (like Wireshark).
  - RETRANSMISSION: a data segment whose last byte was already sent before
    (seq + len <= highest seq + len seen so far).
  - DUPLICATE ACK (RFC 5681 definition): no payload, no SYN/FIN, same
    ACK number AND same advertised window as the previous ACK, while there
    is data outstanding.

Where to capture: on the SENDER host interface you see every transmission,
including packets later dropped at the bottleneck. A capture after the
bottleneck only shows packets that survived.
"""

import argparse
import csv
import struct
import sys

PCAP_MAGIC_MICRO = 0xA1B2C3D4
PCAP_MAGIC_NANO = 0xA1B23C4D
LINKTYPE_ETHERNET = 1
LINKTYPE_LINUX_SLL = 113    # tcpdump -i any

TCP_FIN = 0x01
TCP_SYN = 0x02
TCP_RST = 0x04
TCP_ACK = 0x10

SEQUENCE_COLUMNS = ["time", "direction", "seq", "len", "ack", "window",
                    "retransmission", "dupack", "dupack_count"]


# ---------------------------------------------------------------------------
# Reading the pcap file
# ---------------------------------------------------------------------------
def read_pcap(path):
    """Return a list of TCP/IPv4 packets as dicts. Other packets are skipped."""
    with open(path, "rb") as handle:
        data = handle.read()
    return parse_pcap_bytes(data)


def parse_pcap_bytes(data):
    if len(data) < 24:
        raise ValueError("file too short to be a pcap")

    # Global header: magic, version, timezone, sigfigs, snaplen, linktype.
    # The magic number tells us the byte order and the timestamp unit.
    magic_little = struct.unpack("<I", data[0:4])[0]
    if magic_little in (PCAP_MAGIC_MICRO, PCAP_MAGIC_NANO):
        order = "<"
        magic = magic_little
    else:
        order = ">"
        magic = struct.unpack(">I", data[0:4])[0]
        if magic not in (PCAP_MAGIC_MICRO, PCAP_MAGIC_NANO):
            raise ValueError("not a pcap file (pcapng is not supported, use tcpdump -w)")
    if magic == PCAP_MAGIC_NANO:
        fraction_unit = 1e-9
    else:
        fraction_unit = 1e-6
    linktype = struct.unpack(order + "I", data[20:24])[0]

    packets = []
    offset = 24
    while offset + 16 <= len(data):
        ts_sec, ts_frac, captured_len, _original_len = struct.unpack(
            order + "IIII", data[offset:offset + 16])
        offset = offset + 16
        frame = data[offset:offset + captured_len]
        offset = offset + captured_len
        timestamp = ts_sec + ts_frac * fraction_unit
        packet = parse_frame(frame, linktype, timestamp)
        if packet is not None:
            packets.append(packet)
    return packets


def parse_frame(frame, linktype, timestamp):
    """Ethernet (or Linux cooked) frame -> TCP packet dict, or None."""
    if linktype == LINKTYPE_ETHERNET:
        if len(frame) < 14:
            return None
        ethertype = struct.unpack("!H", frame[12:14])[0]
        ip_start = 14
        if ethertype == 0x8100:            # VLAN tag: skip 4 more bytes
            ethertype = struct.unpack("!H", frame[16:18])[0]
            ip_start = 18
    elif linktype == LINKTYPE_LINUX_SLL:
        if len(frame) < 16:
            return None
        ethertype = struct.unpack("!H", frame[14:16])[0]
        ip_start = 16
    else:
        return None
    if ethertype != 0x0800:                # IPv4 only
        return None
    return parse_ipv4_tcp(frame[ip_start:], timestamp)


def parse_ipv4_tcp(ip, timestamp):
    if len(ip) < 20:
        return None
    version_ihl = ip[0]
    ip_header_len = (version_ihl & 0x0F) * 4
    total_len = struct.unpack("!H", ip[2:4])[0]
    protocol = ip[9]
    if protocol != 6:                      # 6 = TCP
        return None
    src_ip = ".".join(str(b) for b in ip[12:16])
    dst_ip = ".".join(str(b) for b in ip[16:20])

    tcp = ip[ip_header_len:]
    if len(tcp) < 20:
        return None
    src_port, dst_port, seq, ack = struct.unpack("!HHII", tcp[0:12])
    tcp_header_len = (tcp[12] >> 4) * 4
    flags = tcp[13]
    window = struct.unpack("!H", tcp[14:16])[0]
    # Payload length comes from the IP header, so it is right even though
    # tcpdump only saved the first 96 bytes of each packet.
    payload_len = total_len - ip_header_len - tcp_header_len
    return {
        "time": timestamp, "src_ip": src_ip, "dst_ip": dst_ip,
        "src_port": src_port, "dst_port": dst_port, "seq": seq, "ack": ack,
        "flags": flags, "window": window, "len": payload_len,
    }


# ---------------------------------------------------------------------------
# Analysing one connection
# ---------------------------------------------------------------------------
def find_main_flow(packets, sender_ip):
    """
    The connection from sender_ip that carried the most payload.
    (iperf3 also has a small control connection we want to skip.)
    Returns (src_ip, src_port, dst_ip, dst_port) or None.
    """
    bytes_per_flow = {}
    for packet in packets:
        if packet["src_ip"] != sender_ip:
            continue
        key = (packet["src_ip"], packet["src_port"], packet["dst_ip"], packet["dst_port"])
        bytes_per_flow[key] = bytes_per_flow.get(key, 0) + packet["len"]
    best = None
    best_bytes = -1
    for key in bytes_per_flow:
        if bytes_per_flow[key] > best_bytes:
            best_bytes = bytes_per_flow[key]
            best = key
    return best


def analyse_flow(packets, flow):
    """
    Build the time-sequence rows and a summary for one connection.
    flow = (sender_ip, sender_port, receiver_ip, receiver_port)
    """
    sender_ip, sender_port, receiver_ip, receiver_port = flow
    rows = []
    base_seq = None          # first sequence number -> relative 0
    first_time = None
    highest_end = 0          # highest (relative seq + len) sent so far
    last_ack = None
    last_window = None
    dupack_count = 0
    summary = {"data_packets": 0, "data_bytes": 0, "retransmissions": 0,
               "retransmitted_bytes": 0, "acks": 0, "dupacks": 0,
               "longest_dupack_run": 0, "duration_s": 0.0}

    for packet in packets:
        is_data_direction = (packet["src_ip"] == sender_ip and packet["src_port"] == sender_port
                             and packet["dst_ip"] == receiver_ip
                             and packet["dst_port"] == receiver_port)
        is_ack_direction = (packet["src_ip"] == receiver_ip and packet["src_port"] == receiver_port
                            and packet["dst_ip"] == sender_ip
                            and packet["dst_port"] == sender_port)
        if not is_data_direction and not is_ack_direction:
            continue
        if first_time is None:
            first_time = packet["time"]
        time_s = round(packet["time"] - first_time, 6)

        if is_data_direction:
            if base_seq is None:
                if packet["flags"] & TCP_SYN:
                    base_seq = packet["seq"] + 1     # SYN uses one sequence number
                else:
                    base_seq = packet["seq"]         # capture started mid-connection
            if packet["len"] <= 0:
                continue                              # pure ACKs / SYN from the sender
            # "% 2**32" handles the 32-bit sequence number wrapping around
            rel_seq = (packet["seq"] - base_seq) % (2 ** 32)
            end = rel_seq + packet["len"]
            # Retransmission: we have already sent the last byte of this segment
            is_retransmission = end <= highest_end
            if is_retransmission:
                summary["retransmissions"] += 1
                summary["retransmitted_bytes"] += packet["len"]
            else:
                highest_end = end
            summary["data_packets"] += 1
            summary["data_bytes"] += packet["len"]
            rows.append({"time": time_s, "direction": "DATA", "seq": rel_seq,
                         "len": packet["len"], "ack": "", "window": packet["window"],
                         "retransmission": 1 if is_retransmission else 0,
                         "dupack": 0, "dupack_count": 0})
        else:
            if base_seq is None or not (packet["flags"] & TCP_ACK):
                continue
            rel_ack = (packet["ack"] - base_seq) % (2 ** 32)
            summary["acks"] += 1
            control = packet["flags"] & (TCP_SYN | TCP_FIN | TCP_RST)
            outstanding = rel_ack < highest_end
            is_dupack = (packet["len"] == 0 and control == 0 and outstanding
                         and rel_ack == last_ack and packet["window"] == last_window)
            if is_dupack:
                # Same ACK again -> duplicate ACK (3 in a row = fast retransmit)
                dupack_count += 1
                summary["dupacks"] += 1
                if dupack_count > summary["longest_dupack_run"]:
                    summary["longest_dupack_run"] = dupack_count
            elif last_ack is None or rel_ack != last_ack:
                dupack_count = 0
            rows.append({"time": time_s, "direction": "ACK", "seq": "", "len": packet["len"],
                         "ack": rel_ack, "window": packet["window"],
                         "retransmission": 0, "dupack": 1 if is_dupack else 0,
                         "dupack_count": dupack_count})
            last_ack = rel_ack
            last_window = packet["window"]

    if len(rows) > 0:
        summary["duration_s"] = rows[-1]["time"]
    duration = summary["duration_s"]
    if duration > 0:
        # throughput: every payload byte put on the wire, resends included
        summary["throughput_mbps"] = round(summary["data_bytes"] * 8 / duration / 1e6, 4)
        # goodput: distinct bytes (highest byte sent; all were eventually acked
        # if the connection finished normally)
        summary["goodput_mbps"] = round(highest_end * 8 / duration / 1e6, 4)
    else:
        summary["throughput_mbps"] = None
        summary["goodput_mbps"] = None
    summary["unique_bytes"] = highest_end
    return rows, summary


def find_flow_to(packets, sender_ip, receiver_ip, receiver_port):
    """
    Like find_main_flow, but for one server port. Needed when one client runs
    several flows: each flow has its own iperf3 server port. iperf3's control
    connection uses the SAME port, so we still keep the biggest connection.
    """
    bytes_per_flow = {}
    for packet in packets:
        if (packet["src_ip"] != sender_ip or packet["dst_ip"] != receiver_ip
                or packet["dst_port"] != receiver_port):
            continue
        key = (packet["src_ip"], packet["src_port"], packet["dst_ip"], packet["dst_port"])
        bytes_per_flow[key] = bytes_per_flow.get(key, 0) + packet["len"]
    best = None
    best_bytes = -1
    for key in bytes_per_flow:
        if bytes_per_flow[key] > best_bytes:
            best_bytes = bytes_per_flow[key]
            best = key
    return best


def count_spurious_at_receiver(packets, flow):
    """
    Use a capture taken AT THE RECEIVER to find unnecessary retransmissions.

    The receiver's ACK number says "I have every byte below this". If a data
    segment arrives whose last byte is already below the ACK the receiver
    sent, the receiver had those bytes: that copy was not needed (spurious).
    The sender cannot know this, which is why the simulator counts it at
    its receiver too.

    Limitation: a resent segment that was already buffered out of order
    (above the ACK) is not detected. Without SACK, Linux resends only the
    first missing segment per partial ACK, so this case is rare.
    """
    sender_ip, sender_port, receiver_ip, receiver_port = flow
    base_seq = None
    highest_ack = 0        # highest relative ACK the receiver has sent so far
    spurious = 0
    spurious_bytes = 0
    arrived = 0
    for packet in packets:
        is_data_direction = (packet["src_ip"] == sender_ip and packet["src_port"] == sender_port
                             and packet["dst_ip"] == receiver_ip
                             and packet["dst_port"] == receiver_port)
        is_ack_direction = (packet["src_ip"] == receiver_ip and packet["src_port"] == receiver_port
                            and packet["dst_ip"] == sender_ip
                            and packet["dst_port"] == sender_port)
        if is_data_direction:
            if base_seq is None:
                if packet["flags"] & TCP_SYN:
                    base_seq = packet["seq"] + 1
                else:
                    base_seq = packet["seq"]
            if packet["len"] <= 0:
                continue
            arrived += 1
            end = (packet["seq"] - base_seq) % (2 ** 32) + packet["len"]
            if end <= highest_ack:
                spurious += 1
                spurious_bytes += packet["len"]
        elif is_ack_direction:
            if base_seq is None or not (packet["flags"] & TCP_ACK):
                continue
            rel_ack = (packet["ack"] - base_seq) % (2 ** 32)
            # Only move forward; the 2**31 test ignores the wrapped value of
            # the SYN-ACK's ACK, which comes before base_seq is meaningful
            if rel_ack > highest_ack and rel_ack < 2 ** 31:
                highest_ack = rel_ack
    return {"arrived_data_packets": arrived, "spurious_retransmissions": spurious,
            "spurious_bytes": spurious_bytes}


def count_data_packets(packets, flow):
    """Number of payload-carrying packets of one connection in one capture."""
    sender_ip, sender_port, receiver_ip, receiver_port = flow
    count = 0
    for packet in packets:
        if (packet["src_ip"] == sender_ip and packet["src_port"] == sender_port
                and packet["dst_ip"] == receiver_ip and packet["dst_port"] == receiver_port
                and packet["len"] > 0):
            count += 1
    return count


def write_sequence_csv(rows, path):
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEQUENCE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="pcap -> TCP time-sequence CSV")
    parser.add_argument("pcap")
    parser.add_argument("--sender", required=True, help="IP address of the data sender")
    parser.add_argument("--out", required=True, help="CSV file to write")
    args = parser.parse_args()

    packets = read_pcap(args.pcap)
    flow = find_main_flow(packets, args.sender)
    if flow is None:
        print("No TCP data from " + args.sender + " in " + args.pcap)
        return 1
    rows, summary = analyse_flow(packets, flow)
    write_sequence_csv(rows, args.out)
    print("flow " + str(flow))
    for key in summary:
        print("  " + key + ": " + str(summary[key]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
