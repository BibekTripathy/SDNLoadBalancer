# TCP Congestion Control Lab

An add-on to the SDN load balancer that compares **TCP Tahoe, Reno and New Reno**.
It has two parts that check each other:

| Part | Where | What it gives | Algorithms |
|---|---|---|---|
| **A. Simulator** | `tcp_lab/simulator/` | exact, repeatable per-packet traces | Tahoe, Reno, New Reno |
| **B. Mininet** | `tcp_lab/mininet/` | real Linux kernel TCP over OVS + tc | `linux_reno` only |

Every result is labelled with its source (`"source": "simulator"` or `"source": "mininet"`).

> **Honest limitation:** Linux has no Tahoe. Linux `reno` with SACK turned off
> recovers like **New Reno** (partial ACKs keep it in fast recovery, RFC 6582).
> So Tahoe and classic Reno numbers come only from the simulator; Mininet is the
> real-world check for the New Reno-style behaviour.

*(The full README section — architecture, every scenario, and a viva-style
explanation of each algorithm — is written in Phase 8.)*

## The ssthresh rule (simulator)

```
ssthresh = max(window / 2, 2 segments)
```

ssthresh changes at **exactly two moments**, nowhere else
(`CongestionControlBase.half_window()` in `simulator/base.py`):

1. **3rd duplicate ACK** (fast retransmit), only when the sender is **not**
   already in fast recovery. `window` = cwnd.
2. **Retransmission timeout.** `window` = cwnd, **except inside fast recovery**:
   there cwnd has been inflated by one segment per extra dup ACK, so the real
   window is ssthresh, and the timeout halves **ssthresh** again.

Inside fast recovery, extra dup ACKs and New Reno's partial ACKs **never** change
ssthresh; they only inflate (+1) or deflate (−newly acked +1) cwnd.

A consequence worth knowing for the viva: **Reno with two losses in one window**
leaves fast recovery on the first partial ACK, then gets 3 new dup ACKs for the
second hole and halves again (e.g. ssthresh 10.5 → 5.25). New Reno halves once.

Why cwnd/2 and not FlightSize/2 (RFC 5681)? They are equal while the sender is
window-limited. But just after Reno's inflated fast recovery, FlightSize can be far
larger than cwnd and would *raise* ssthresh on the next loss. Halving cwnd is what
4.3BSD Reno and ns-2 do. (Linux reno uses `max(cwnd/2, 2)` as well.)

## Part A — simulator

```bash
.venv/bin/python -m tcp_lab.run_sim_scenarios                 # all scenarios, 5 seeds (~1 min)
.venv/bin/python -m tcp_lab.run_sim_scenarios --scenario S2   # one scenario
.venv/bin/python -m tcp_lab.run_sim_scenarios --seeds 10      # more seeds for random loss
.venv/bin/python -m pytest tests/test_tcp_sim.py tests/test_tcp_lab_runner.py
```

Output: `results/<scenario>/<variant>/` with one event CSV per algorithm, `cwnd.png`,
`sequence.png` (+ `sequence_zoom.png` for S1/S2), `rtt.png`, `throughput.png`,
`timeseries.json`; and `results/<scenario>/summary.json`.

Random-loss variants (S3, S6, S6Q) run with seeds 1-5; only seed 1 gets the CSV
and plots, every seed adds a row to `seed_results`. Variants without random loss
give the same result for every seed and run once. For the scenarios that also run
on Mininet, Reno and New Reno run once more with an unlimited initial ssthresh
(`linux_start_results`), because that is how Linux starts (see Phase 5).

Simulator simplifications: segments (not bytes); no delayed ACKs; the ACK path has
no queue and no loss; a duplicate ACK caused by a *retransmitted* segment is not
counted (only an old copy arrived twice — the idea of RFC 6582's timestamp heuristic).

## Part B — Mininet (real Linux TCP)

All code in `tcp_lab/mininet/` uses only the Python standard library, so it runs
under `sudo python3` with the system Python that has Mininet.

**Needs:** Mininet, Open vSwitch, `iperf3`, `tcpdump`, `ethtool`, `iproute2` (`tc`, `ss`, `nstat`).

```bash
scripts/run_tcp_lab_smoke.sh                    # dumbbell, OVS as a learning switch
scripts/run_tcp_lab_smoke.sh --controller ryu   # dumbbell switches controlled by Ryu on :6653
scripts/run_tcp_lab_smoke.sh --target vip       # client -> VIP 10.0.0.100 through the LB
python3 -m pytest tests/test_tcp_lab_mininet.py # parser / command-builder unit tests (no root)
```

The smoke test runs one 20 s Linux reno flow over a 10 Mbit/s, 10 ms (each way)
bottleneck, steps the bandwidth down to 3 Mbit/s half way, and prints PASS/FAIL
checks plus the retransmission count from four independent sources (iperf3, nstat,
ss, pcap), which should agree.

### Topology (dumbbell)

```
c1 10.0.0.11 --\                                   /-- sv1 10.0.0.21
c2 10.0.0.12 ---- sw1 ==== bottleneck (TCLink) ==== sw2
c3 10.0.0.13 --/  eth1                         eth1 \-- sv2 10.0.0.22
```

Switches are named `sw1`/`sw2` (not `s1`) so the dashboard API, which checks for a
bridge called `s1`, does not mistake the lab for the load-balancer network.

**VIP mode** builds the project's own load-balancer topology (stop the
`run_mininet.sh` CLI first; keep the Ryu LB running). iperf3 cannot be used through
the VIP: it opens a control and a data connection from different source ports and
the LB may send them to different backends. `bulk_tcp.py` uses one connection
(TCP) or one socket (UDP) instead.

### Scenarios S3-S6 on Mininet (Phase 4)

```bash
scripts/run_tcp_lab_mininet.sh                          # S3-S6, 3 runs per variant (~15 min)
scripts/run_tcp_lab_mininet.sh --scenario S3 --runs 5   # one scenario, 5 runs
scripts/run_tcp_lab_mininet.sh --scenario S4 --variant 2_flows
scripts/run_tcp_lab_mininet.sh --controller ryu         # dumbbell switches under Ryu
python3 -m pytest tests/test_tcp_lab_mininet_runner.py  # no root needed
```

The Mininet plans are **built from the simulator's scenario definitions**
(`mininet/scenarios.py`), so both parts use the same bandwidth, one-way delay
(added in each direction, so the base RTT is 2 x delay), queue, loss, flow start
times and S5 bandwidth steps. S1/S2 are simulator only: netem drops packets at
random and cannot drop one chosen segment.

S4 spreads its flows over the hosts: flow *i* goes from client `i % 3` to server
`i % 2` on its own iperf3 port (5201 + *i*); the UDP background goes c3 -> sv2
(ports 5301+).

**Repeated runs.** Real runs are not repeatable (timer and scheduling noise
changes which packets are lost), so every variant runs `--runs` times
(default 3). Run *N* uses `netem ... seed N`, so its random-loss *pattern* can
be repeated. Phase 5 averages the runs.

**Output** (next to the simulator results, never overwriting them):

```
results/<S>/mininet_summary.json                 one result row per run ("source": "mininet")
results/<S>/<variant>/mininet_run<N>/
    flow<i>_iperf3.json  udp<j>_iperf3.json      raw iperf3 reports
    ss_<client>.csv                              kernel cwnd / ssthresh / RTT every 50 ms
    <host>.pcap  flow<i>_seq.csv                 captures + sender time-sequence
    run.json                                     everything parsed from this run
```

Where every Mininet number comes from (stored with the result):

| Number | Source |
|---|---|
| goodput | iperf3 servers: bytes the application read / experiment length |
| throughput | pcap **at the server**: payload bytes that arrived, resends included |
| retransmissions | iperf3 (sender kernel); nstat and the sender pcap as cross-checks |
| spurious / needed | pcap at the server: a resend whose bytes the receiver had **already ACKed** is spurious; needed = total - spurious |
| timeouts, fast retransmits, recoveries | nstat on the clients |
| queue drops / random drops | `tc -s` on the bottleneck (tbf = queue full, netem - tbf = random loss) |
| RTT | ss: the kernel's smoothed RTT, sampled every 50 ms (not per packet as in the simulator) |

**Two Mininet details fixed in Phase 4:**

- *initcwnd 1 did not apply in the smoke test* (ss showed a first cwnd of 10).
  Mininet runs host commands on a terminal, and iproute2 then **colours**
  `ip route show`; the colour codes broke the `ip route change` command, and
  nothing reported it. The route table is now read through a pipe
  (`ip route show | cat`) and checked afterwards.
- *"first cwnd 10" in the first S3 runs was a measuring mistake, not a setup
  one* (the pcaps show slow start from 1: cookie, then 2, then 4 segments).
  The first ss sample of each connection was taken during the handshake
  (`SYN-SENT`), where Linux shows its default cwnd of 10; it sets cwnd to the
  route's initcwnd only once the connection is established. The sampler now
  records the TCP state and `delivered`, and the runner works out the
  **initial cwnd** from the first established sample: in slow start Linux adds
  one segment per segment ACKed, so `initial cwnd = cwnd - (delivered - 1)`
  (`delivered` counts the SYN). Checked on the real kernel: 1 at every
  slow-start sample with initcwnd 1, 10 with the default. If any flow's
  initial cwnd is not 1, or any host setting is wrong, the runner **stops**
  (exit code 2) and does not store that run; the smoke test prints FAIL and
  exits 1.
- `mininet.clean.cleanup()` (`mn -c`) calls the obsolete `egrep`, removes every
  OVS bridge and kills every `ryu-manager`. The lab uses its own
  `mininet/cleanup.py` (with `grep -E`), which only removes the lab's own
  switches, links and host shells.

### What each file does

| File | Job |
|---|---|
| `host_setup.py` | `tcp_congestion_control=reno`, `tcp_sack=0`, `tcp_no_metrics_save=1`, TLP / RACK / F-RTO / ECN off, `ethtool -K tso/gso/gro off`, optional `initcwnd 1` |
| `tc_controller.py` | `netem` (delay, jitter, random or burst loss) with a `tbf` child (bandwidth + drop-tail queue), changed at runtime with `tc qdisc replace` |
| `ss_sampler.py` | polls `ss -tin` every 50 ms → cwnd, ssthresh, rtt, rttvar, rto, bytes_acked, retrans, lost, delivery rate |
| `pcap_parser.py` | pure-Python pcap reader → time-sequence CSV with retransmissions and dup ACKs |
| `traffic.py` | iperf3 / tcpdump / nstat commands and parsers |
| `bulk_tcp.py` | single-connection TCP/UDP sender + receiver for the VIP |
| `scenarios.py` | S3-S6 as Mininet plans (tc conditions, flows, UDP, timeline) |
| `cleanup.py` | removes leftovers of a crashed run, lab names only |
| `../run_mininet_scenarios.py` | runs the plans N times and writes the results |

Linux receivers use **delayed ACKs** (about one ACK per two segments), unlike the
simulator, so dup ACK counts are not directly comparable between the two parts.

## Phase 5 - analysis, scoring, recommendation

```bash
.venv/bin/python -m tcp_lab.run_sim_scenarios     # simulator results (5 seeds)
.venv/bin/python -m tcp_lab.run_analysis          # reads simulator + Mininet results
.venv/bin/python -m pytest tests/test_tcp_lab_analysis.py
```

Writes `results/analysis/report.md` (all tables and explanations),
`analysis.json` (every number, labelled `simulator`, `mininet` or `model`) and
plots (`<S>_comparison.png`, `s6_goodput_vs_rtt.png`).

| File | Job |
|---|---|
| `analysis/stats.py` | n, mean, median, std, min, max of repeated runs |
| `analysis/metrics.py` | also: recovery time, same definition for simulator and pcap |
| `analysis/scoring.py` | points for *clear* wins, recommendation (simulator only) |
| `analysis/compare.py` | Mininet vs simulator, the Mathis formula |
| `analysis/report.py` | the Markdown report |
| `run_analysis.py` | runs all of the above |

**Never ranked on one run.** Every metric is reported as mean (median, min-max, n).
The median is there because one bad run can pull the mean a long way (S6 rtt_10ms
on Mininet: 80, 198 and 786 retransmissions: mean 355, median 198).

**Recovery time** = from the first resend after a loss until everything that was
sent before that resend is ACKed. The same function works on the simulator log
(segments) and on a pcap time-sequence (bytes).

**Scoring (simulator only; Linux has no Tahoe).** For every variant and metric, A
gets `weight` points for each algorithm it *clearly* beats: its mean must be
better by more than `max(std A, std B, 2 % of the larger mean)`. So noise cannot
decide a ranking, and in scenarios without randomness a 0.1 % difference is a
tie. Weights: goodput 3, timeouts 2, recovery time 2, spurious resends 1,
retransmissions 1, P95 RTT 1, fairness 1 (several flows only). The algorithm with
the most points over S1-S6 is recommended.

**Validation (mininet vs simulator).** Linux is compared with simulator runs that
start like Linux (no initial ssthresh). The normal simulator runs start with
ssthresh 32 and never overshoot, while Linux's first slow start overshoots the
queue on a clean link. That difference alone explained most of the early gap
(S4 1_flow: Linux 7.0, simulator 9.6 with ssthresh 32, 7.4 with a Linux-like
start).

**S6, delay or queue?** At random loss p a Reno-style flow keeps on average only
about `C/sqrt(p)` segments in flight (Mathis et al.), about 17 at 0.5 %, whatever
the RTT. At 10 ms RTT the link needs only about 9 segments (the bandwidth-delay
product), so it stays full. At 50 ms it needs 43, so goodput falls to about
`window x MSS / RTT`. Check S6Q runs S6 rtt_50ms with queues of 25, 100 and 400
packets and once without loss: in the simulator the queue changes nothing and
removing the loss restores the link rate. On Mininet the queue only adds
run-to-run spread, through the first slow start's overshoot.

