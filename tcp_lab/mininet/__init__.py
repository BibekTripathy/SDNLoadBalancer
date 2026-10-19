"""
Real TCP traffic through Mininet (Linux kernel TCP, not simulated).

Linux has no Tahoe. Its "reno" module with SACK turned off recovers like
New Reno (RFC 6582), so every result from here is labelled "linux_reno".

Everything in this package uses only the Python standard library, so it
runs under `sudo python3` on a Mininet machine without the project venv.

  hosts.py          - names and IP addresses of the dumbbell hosts (no mininet import)
  dumbbell_topo.py  - 3 clients, 2 servers, one bottleneck link (and the VIP mode topology)
  scenarios.py      - S3-S6 as Mininet plans, built from the simulator's scenarios
  cleanup.py        - removes leftovers of a crashed run (only the lab's own nodes)
  host_setup.py     - sysctl / ethtool / ip route commands that make Linux TCP "textbook"
  tc_controller.py  - tc netem + tbf commands to change delay, loss, bandwidth at runtime
  traffic.py        - iperf3 / tcpdump / nstat command builders and output parsers
  bulk_tcp.py       - single-connection TCP/UDP sender and receiver (for the VIP mode)
  ss_sampler.py     - polls `ss -tin` every 50 ms and writes cwnd/RTT/retransmissions to CSV
  pcap_parser.py    - reads a pcap (pure Python) and writes a seq/ack time-sequence CSV
  smoke_test.py     - one short end-to-end experiment to check that everything works

The scenario runner itself is tcp_lab/run_mininet_scenarios.py (next to
run_sim_scenarios.py).
"""
