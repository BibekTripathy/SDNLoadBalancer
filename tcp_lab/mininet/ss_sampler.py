"""
Sample the kernel's TCP state with `ss -tin` every 50 ms and save it to CSV.

`ss -tin` prints, for every TCP socket, a line with the addresses and an
indented line with internal variables, for example:

    ESTAB 0  2531840  10.0.0.11:54708  10.0.0.21:5201
         reno wscale:9,9 rto:204 rtt:20.04/7.51 mss:1448 cwnd:12 ssthresh:7
         bytes_sent:110117 bytes_retrans:2896 bytes_acked:98000 ...
         delivery_rate 8790136bps ... unacked:12 retrans:1/3 lost:1

We keep: the TCP state, cwnd, ssthresh, rtt, rttvar, rto, mss, bytes_sent,
bytes_acked, bytes_retrans, retrans (now/total), lost, unacked, delivered
(segments ACKed so far, the SYN included) and delivery_rate.

The state matters: while the handshake is still running (SYN-SENT) Linux
shows its default cwnd of 10. Only when the connection is ESTABLISHED does
it set cwnd to the route's initcwnd (1 in this lab).

Run it inside the sending Mininet host, e.g.
    c1.popen("python3 -m tcp_lab.mininet.ss_sampler --dst 10.0.0.21 "
             "--duration 30 --out results/S3/loss_1pct/mininet_ss.csv")
"""

import argparse
import csv
import subprocess
import sys
import time

SS_COLUMNS = [
    "time", "local", "peer", "state", "cc", "cwnd", "ssthresh", "rtt_ms", "rttvar_ms",
    "rto_ms", "mss", "bytes_sent", "bytes_acked", "bytes_retrans",
    "retrans_now", "retrans_total", "lost", "unacked", "delivered", "delivery_rate_mbps",
]

TCP_STATES = ["ESTAB", "SYN-SENT", "SYN-RECV", "FIN-WAIT-1", "FIN-WAIT-2",
              "TIME-WAIT", "CLOSE-WAIT", "LAST-ACK", "CLOSING", "LISTEN", "UNCONN"]

CC_NAMES = ["reno", "cubic", "bbr", "htcp", "vegas", "westwood", "highspeed", "dctcp"]

# "key:value" fields copied as integers
INTEGER_FIELDS = ["cwnd", "ssthresh", "mss", "bytes_sent", "bytes_acked",
                  "bytes_retrans", "lost", "unacked", "delivered"]


def parse_rate_mbps(text):
    """'8790136bps' -> 8.79, '9.5Mbps' -> 9.5, '120Kbps' -> 0.12, '1.2Gbps' -> 1200."""
    if text.endswith("Gbps"):
        return float(text[:-4]) * 1000.0
    if text.endswith("Mbps"):
        return float(text[:-4])
    if text.endswith("Kbps"):
        return float(text[:-4]) / 1000.0
    if text.endswith("bps"):
        return float(text[:-3]) / 1e6
    return None


def empty_sample():
    sample = {}
    for column in SS_COLUMNS:
        sample[column] = None
    return sample


def parse_info_line(sample, line):
    """Fill `sample` from the indented line of internal TCP variables."""
    words = line.split()
    index = 0
    while index < len(words):
        word = words[index]
        if ":" in word:
            key, value = word.split(":", 1)
            if key in INTEGER_FIELDS:
                sample[key] = int(value)
            elif key == "rtt":
                # rtt:20.044/7.519 -> smoothed RTT / RTT variation, in ms
                rtt, rttvar = value.split("/")
                sample["rtt_ms"] = float(rtt)
                sample["rttvar_ms"] = float(rttvar)
            elif key == "rto":
                sample["rto_ms"] = float(value)
            elif key == "retrans":
                # retrans:1/3 -> 1 retransmitted segment not yet acked, 3 in total
                now, total = value.split("/")
                sample["retrans_now"] = int(now)
                sample["retrans_total"] = int(total)
        elif word == "delivery_rate" and index + 1 < len(words):
            # "delivery_rate 8790136bps" is two words
            sample["delivery_rate_mbps"] = parse_rate_mbps(words[index + 1])
            index = index + 1
        elif word in CC_NAMES:
            sample["cc"] = word
        index = index + 1


def split_address(text):
    """'[::ffff:10.0.0.1]:5201' or '10.0.0.1:5201' -> ('10.0.0.1', 5201)."""
    host, port = text.rsplit(":", 1)
    host = host.strip("[]")
    host = host.removeprefix("::ffff:")   # IPv4 address shown in IPv6 form
    return host, int(port)


def parse_ss_output(text, timestamp=0.0):
    """Turn one `ss -tin` output into a list of sample dicts (one per socket)."""
    samples = []
    current = None
    for line in text.splitlines():
        if line.strip() == "":
            continue
        words = line.split()
        if words[0] in TCP_STATES and len(words) >= 5:
            # New socket: State Recv-Q Send-Q Local:Port Peer:Port
            current = empty_sample()
            current["time"] = timestamp
            current["state"] = words[0]
            current["local"] = words[3]
            current["peer"] = words[4]
            samples.append(current)
        elif line[0] in " \t" and current is not None:
            parse_info_line(current, line)
        # anything else (the header line) is ignored
    return samples


def pick_main_flow(samples):
    """
    iperf3 opens a small control connection next to the data connection.
    Return the local address of the socket that SENT the most data.
    (bytes_sent, not bytes_acked: a data connection stuck in a timeout can
    have fewer bytes acked than the control connection.)
    """
    best_local = None
    best_bytes = -1
    for sample in samples:
        sent = sample["bytes_sent"]
        if sent is None:
            continue
        if sent > best_bytes:
            best_bytes = sent
            best_local = sample["local"]
    return best_local


def pick_flow_to(samples, peer_ip, peer_port):
    """
    Like pick_main_flow, but only sockets talking to one server ip:port.
    Used when one client runs several flows (one iperf3 server port each).
    """
    matching = []
    for sample in samples:
        if split_address(sample["peer"]) == (peer_ip, peer_port):
            matching.append(sample)
    return pick_main_flow(matching)


def samples_of(samples, local):
    """All samples of one socket (one local address:port), in time order."""
    result = []
    for sample in samples:
        if sample["local"] == local:
            result.append(sample)
    return result


def first_established_sample(samples):
    """
    The first sample taken after the handshake. A socket in SYN-SENT still
    shows Linux's default cwnd (10) and has no RTT yet. CSVs written before
    the "state" column existed have no state, so "has an RTT" is used too.
    """
    for sample in samples:
        state = sample.get("state")
        if state is not None and state != "ESTAB":
            continue
        if sample["rtt_ms"] is None:
            continue
        return sample
    return None


def estimate_initial_cwnd(samples):
    """
    The cwnd the connection STARTED with, from its first established sample.

    A 50 ms sampler usually misses the moment cwnd is exactly 1 (with a
    40 ms RTT, cwnd may already be 2 or 4). But in slow start Linux adds
    one segment to cwnd for every segment ACKed, so before the first loss:

        initial cwnd = cwnd now - data segments ACKed so far
                     = cwnd - (delivered - 1)        (delivered counts the SYN)

    Example from a real run: cwnd 2, delivered 2 (SYN + iperf3's 37-byte
    cookie) -> 2 - 1 = 1.

    Returns None when it cannot be worked out: no established sample, an
    old CSV without "delivered", or a loss already happened (ssthresh set).
    """
    sample = first_established_sample(samples)
    if sample is None:
        return None
    if sample.get("delivered") is None or sample["cwnd"] is None:
        return None
    if sample["ssthresh"] is not None:
        return None          # slow start already ended, the rule no longer holds
    return int(sample["cwnd"] - (sample["delivered"] - 1))


def read_samples_csv(path):
    """Read a CSV written by this sampler back into dicts with numbers."""
    rows = []
    with open(path) as handle:
        for row in csv.DictReader(handle):
            for key in row:
                if key in ("local", "peer", "state", "cc"):
                    continue
                if row[key] == "":
                    row[key] = None
                else:
                    row[key] = float(row[key])
            rows.append(row)
    return rows


def run_sampler(dst_ip, duration, interval, out_path):
    """Poll ss until `duration` seconds have passed, appending rows to out_path."""
    start = time.time()
    with open(out_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SS_COLUMNS)
        writer.writeheader()
        while True:
            now = time.time() - start
            if now > duration:
                break
            result = subprocess.run(["ss", "-tin", "dst", dst_ip],
                                    capture_output=True, text=True, check=False)
            for sample in parse_ss_output(result.stdout, round(now, 4)):
                writer.writerow(sample)
            handle.flush()
            # Sleep until the next 50 ms tick (ss itself takes a few ms)
            next_tick = start + (int(now / interval) + 1) * interval
            sleep_for = next_tick - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)


def main():
    parser = argparse.ArgumentParser(description="Sample ss -tin into a CSV")
    parser.add_argument("--dst", required=True, help="peer IP to watch (server or VIP)")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=0.05, help="seconds, default 50 ms")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_sampler(args.dst, args.duration, args.interval, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
