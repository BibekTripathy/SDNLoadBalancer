"""
Minimal bulk TCP / UDP sender and receiver, used for the VIP experiments.

Why not iperf3 through the VIP? iperf3 opens TWO connections (a control
connection and a data connection) from different source ports. The SDN
load balancer picks a backend per (client IP, client port), so the two
connections can land on different backend servers and the test fails.
This tool uses exactly one TCP connection (or one UDP socket).

Receiver (run on every backend server):
    python3 -m tcp_lab.mininet.bulk_tcp recv --port 5001

TCP sender (run on the client, sends for 20 s with Reno):
    python3 -m tcp_lab.mininet.bulk_tcp send --host 10.0.0.100 --port 5001 --time 20 --cc reno

UDP sender (2 Mbit/s of 1400-byte datagrams):
    python3 -m tcp_lab.mininet.bulk_tcp send --host 10.0.0.100 --port 5001 --time 20 --udp --rate 2

The sender prints one JSON line with what it did. Goodput is best taken
from the ss sampler (bytes_acked), because "bytes written" also counts
data still sitting in the socket buffer.
"""

import argparse
import json
import socket
import sys
import threading
import time

CHUNK_BYTES = 65536
UDP_PAYLOAD_BYTES = 1400


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------
def handle_tcp_connection(connection, address):
    total = 0
    start = time.time()
    while True:
        data = connection.recv(CHUNK_BYTES)
        if not data:
            break
        total = total + len(data)
    connection.close()
    seconds = time.time() - start
    print(json.dumps({"proto": "tcp", "peer": address[0], "port": address[1],
                      "bytes_received": total, "seconds": round(seconds, 3)}), flush=True)


def tcp_receiver(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(16)
    while True:
        connection, address = server.accept()
        worker = threading.Thread(target=handle_tcp_connection, args=(connection, address))
        worker.daemon = True
        worker.start()


def udp_receiver(port):
    """Count datagrams; after 1 s of silence print what one burst delivered."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)
    datagrams = 0
    total = 0
    peer = None
    while True:
        try:
            data, address = sock.recvfrom(CHUNK_BYTES)
        except TimeoutError:
            if datagrams > 0:
                print(json.dumps({"proto": "udp", "peer": peer, "datagrams_received": datagrams,
                                  "bytes_received": total}), flush=True)
                datagrams = 0
                total = 0
            continue
        datagrams = datagrams + 1
        total = total + len(data)
        peer = address[0]


def run_receiver(port):
    udp_thread = threading.Thread(target=udp_receiver, args=(port,))
    udp_thread.daemon = True
    udp_thread.start()
    tcp_receiver(port)


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------
def send_tcp(host, port, seconds, cc):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Choose the congestion control algorithm for this one socket
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, cc.encode())
    sock.connect((host, port))
    chunk = b"x" * CHUNK_BYTES
    written = 0
    start = time.time()
    while time.time() - start < seconds:
        sock.sendall(chunk)
        written = written + len(chunk)
    sock.close()
    return {"proto": "tcp", "cc": cc, "bytes_written": written,
            "seconds": round(time.time() - start, 3)}


def send_udp(host, port, seconds, rate_mbps):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"u" * UDP_PAYLOAD_BYTES
    gap = UDP_PAYLOAD_BYTES * 8 / (rate_mbps * 1e6)   # seconds between datagrams
    sent = 0
    start = time.time()
    next_send = start
    while time.time() - start < seconds:
        sock.sendto(payload, (host, port))
        sent = sent + 1
        next_send = next_send + gap
        sleep_for = next_send - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)
    return {"proto": "udp", "rate_mbps": rate_mbps, "datagrams_sent": sent,
            "seconds": round(time.time() - start, 3)}


def main():
    parser = argparse.ArgumentParser(description="Single-connection bulk TCP/UDP tool")
    sub = parser.add_subparsers(dest="mode", required=True)
    recv = sub.add_parser("recv")
    recv.add_argument("--port", type=int, default=5001)
    send = sub.add_parser("send")
    send.add_argument("--host", required=True)
    send.add_argument("--port", type=int, default=5001)
    send.add_argument("--time", type=float, default=10.0)
    send.add_argument("--cc", default="reno")
    send.add_argument("--udp", action="store_true")
    send.add_argument("--rate", type=float, default=1.0, help="UDP rate in Mbit/s")
    args = parser.parse_args()

    if args.mode == "recv":
        run_receiver(args.port)
        return 0
    if args.udp:
        result = send_udp(args.host, args.port, args.time, args.rate)
    else:
        result = send_tcp(args.host, args.port, args.time, args.cc)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
