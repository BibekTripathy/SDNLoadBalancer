# TCP Congestion Control Lab

An add-on to the SDN load balancer that compares the classic TCP congestion
control algorithms **Tahoe, Reno and New Reno**: how they react to single and
multiple losses, random loss, more traffic, bandwidth changes and longer delays.

It has two parts that check each other:

| Part | Where | What it gives | Algorithms |
|---|---|---|---|
| **A. Simulator** | `tcp_lab/simulator/` | exact, repeatable per-packet traces | Tahoe, Reno, New Reno |
| **B. Mininet** | `tcp_lab/mininet/` | real Linux kernel TCP over Open vSwitch + `tc` | `linux_reno` only |

Every number the lab produces is labelled with where it comes from:
**simulator**, **mininet** (real Linux), or **model** (a formula).

> **Limitations up front.** Linux has no Tahoe. Linux `reno` with SACK turned off
> recovers like **New Reno**, not like classic Reno. So the three-way comparison
> comes **only from the simulator**. Mininet checks the simulator against real
> Linux. Details are under [Limitations](#limitations).

Viva preparation: [VIVA.md](VIVA.md), likely questions answered from our results.

---

## Contents

1. [Quick start](#quick-start)
2. [Architecture](#architecture)
3. [The algorithms, explained](#the-algorithms-explained)
4. [Scenarios and how to run each one](#scenarios-and-how-to-run-each-one)
5. [What is measured](#what-is-measured)
6. [Results and recommendation](#results-and-recommendation)
7. [Limitations](#limitations)
8. [Mininet details](#mininet-details)
9. [Analysis method](#analysis-method)
10. [API and dashboard](#api-and-dashboard)
11. [Files](#files)

---

## Quick start

```bash
# 1. Simulator: all scenarios, 5 seeds for random loss (~1 minute)
.venv/bin/python -m tcp_lab.run_sim_scenarios

# 2. Real Linux in Mininet (needs root, on the Mininet machine, ~20 minutes)
scripts/run_tcp_lab_smoke.sh          # check the setup first
scripts/run_tcp_lab_mininet.sh        # S3-S6 and S6Q, 3 runs per variant

# 3. Statistics, scores, recommendation, comparison
.venv/bin/python -m tcp_lab.run_analysis     # -> results/analysis/report.md

# 4. Dashboard: open the "TCP Lab" tab
.venv/bin/uvicorn api.main:app --port 8000
cd front-end && npm run dev

# Tests (no root needed)
.venv/bin/python -m pytest tests/test_tcp_sim.py tests/test_tcp_lab_*.py
```

`results/` is not in git. Every command above writes into it, and every later step reads from it.

---

## Architecture

```
                 tcp_lab/simulator/scenarios.py   (S1-S6 + S6Q: one definition)
                        |                                   |
                        v                                   v
   +--------------------------------+      +--------------------------------------+
   | A. SIMULATOR (pure Python)     |      | B. MININET (real Linux, needs root)  |
   |  tahoe.py reno.py newreno.py   |      |  mininet/scenarios.py  (same numbers)|
   |  base.py  (shared rules)       |      |  dumbbell_topo.py  host_setup.py     |
   |  rto.py   (RFC 6298 timer)     |      |  tc_controller.py  (netem + tbf)     |
   |  tcp_sim.py (events, link,     |      |  iperf3, tcpdump, ss, nstat          |
   |              receiver)         |      |  pcap_parser.py  ss_sampler.py       |
   |  run_sim_scenarios.py          |      |  run_mininet_scenarios.py            |
   +---------------+----------------+      +------------------+-------------------+
                   |  results/<S>/summary.json                |  results/<S>/mininet_summary.json
                   |  (+ event CSVs, plots)                   |  (+ pcaps, ss CSVs per run)
                   v                                          v
          +------------------------------------------------------------+
          | ANALYSIS  run_analysis.py                                  |
          |  stats.py (mean/median/spread)  scoring.py (clear wins)    |
          |  compare.py (Linux vs simulator, Mathis formula)           |
          |  report.py -> results/analysis/report.md, analysis.json    |
          +-----------------------------+------------------------------+
                                        |
                                        v
          +------------------------------------------------------------+
          | API  api/tcp_lab/  (FastAPI, /api/tcp-lab/...)             |
          |  results.py: read-only access to results/                  |
          |  live.py: TCP_CWND_SAMPLE events over /ws/events           |
          +-----------------------------+------------------------------+
                                        |
                                        v
          +------------------------------------------------------------+
          | DASHBOARD  front-end/src/components/tcplab/  ("TCP Lab")   |
          |  live cwnd chart, results table, recommendation, plots     |
          |  displays only: no TCP logic in the browser                |
          +------------------------------------------------------------+
```

How the simulator works, in one paragraph: it is an **event-driven** simulation.
A priority queue holds future events (a packet reaches the bottleneck, a packet
arrives, an ACK arrives, a timer fires), sorted by time. The main loop takes the
earliest event, runs its handler, and the handler adds new events. The sender
asks its algorithm object (`TahoeSender`, `RenoSender`, `NewRenoSender`) what to
do on every ACK, duplicate ACK and timeout. The bottleneck link has a drop-tail
queue, a bandwidth (serialisation delay) and a propagation delay. The receiver
sends cumulative ACKs and notes which arriving segments it already had (spurious
resends). cwnd, ssthresh and sequence numbers are counted in **segments**.

---

## The algorithms, explained

All three share the same **window growth** and the same **ssthresh rule**
(`simulator/base.py`). They differ only in **what they do after a loss**.

### What they share

- **cwnd** (congestion window): how many segments may be unacknowledged at once.
  The sender may send `min(cwnd, receiver window)` segments beyond the oldest unACKed one.
- **Slow start** (`cwnd < ssthresh`): cwnd grows by 1 for every new ACK, so it
  **doubles every round-trip time**. It starts at 1 segment.
- **Congestion avoidance** (`cwnd >= ssthresh`): cwnd grows by `1/cwnd` per new
  ACK, so about **+1 segment per round-trip time** (additive increase).
- **Loss detection**, two ways:
  - **3 duplicate ACKs**: the receiver keeps ACKing the same byte because a
    segment is missing but later ones arrive. Three in a row means "probably lost",
    and the segment is resent at once (**fast retransmit**).
  - **Retransmission timeout (RTO)**: no ACK for too long. Every algorithm reacts
    the same way: `ssthresh = half`, `cwnd = 1`, slow start, resend from the oldest
    unACKed segment.
- **RTO estimate** (`rto.py`, RFC 6298): `SRTT = 7/8 SRTT + 1/8 sample`,
  `RTTVAR = 3/4 RTTVAR + 1/4 |SRTT - sample|`, `RTO = SRTT + 4 RTTVAR`, minimum
  200 ms, initial 1 s, doubled after every timeout (exponential backoff). Each ACK
  echoes the send time of the segment that caused it, like the TCP timestamp
  option, so even resent segments give correct RTT samples and Karn's rule is not
  needed.

### The ssthresh rule

```
ssthresh = max(window / 2, 2 segments)
```

ssthresh changes at **exactly two moments**, nowhere else
(`CongestionControlBase.half_window()`):

1. **The 3rd duplicate ACK** (fast retransmit), only when the sender is **not**
   already in fast recovery. `window` = cwnd.
2. **A retransmission timeout.** `window` = cwnd, **except inside fast recovery**.
   There cwnd has been inflated by one segment per extra duplicate ACK, so the real
   window is ssthresh, and the timeout halves **ssthresh** again.

Inside fast recovery, extra duplicate ACKs and New Reno's partial ACKs **never**
change ssthresh. They only inflate cwnd (+1) or deflate it (−newly ACKed +1).

Why cwnd/2 and not FlightSize/2 (RFC 5681)? They are equal while the sender is
window-limited. Just after Reno's inflated fast recovery, though, FlightSize can be
far larger than cwnd and would *raise* ssthresh at the next loss. Halving cwnd is
what 4.3BSD Reno and ns-2 do, and Linux reno uses `max(cwnd/2, 2)` as well.

### TCP Tahoe (`simulator/tahoe.py`)

The first algorithm with congestion control (1988).

| Event | What Tahoe does |
|---|---|
| new ACK | slow start or congestion avoidance growth |
| 3rd duplicate ACK | fast retransmit; `ssthresh = cwnd/2`; **`cwnd = 1`**; slow start; **resend everything from the hole onwards** (go-back-N) |
| timeout | same as above |

**In one sentence:** *every* loss sends Tahoe back to cwnd 1.
**Weakness:** after one lost segment the pipe empties and refills from 1 segment.
Go-back-N also resends segments the receiver already has (**spurious
retransmissions**: 3 of 6 resends in S2 with 3 losses).
**Strength:** it never inflates cwnd, so it never pushes a burst into a congested queue.

Worked example from the tests: cwnd 20, one segment lost → ssthresh 10, cwnd 1,
then slow start 1, 2, 4, 8 and congestion avoidance from 10.

### TCP Reno (`simulator/reno.py`)

Tahoe plus **fast recovery** (1990, RFC 5681).

| Event | What Reno does |
|---|---|
| 3rd duplicate ACK | fast retransmit; `ssthresh = cwnd/2`; `cwnd = ssthresh + 3`; enter **fast recovery** |
| more duplicate ACKs (in fast recovery) | `cwnd += 1` (**inflation**: each duplicate ACK means one segment left the network, so one new segment may be sent) |
| first new ACK (in fast recovery) | `cwnd = ssthresh` (**deflation**); leave fast recovery; congestion avoidance |
| timeout | `cwnd = 1`, slow start |

**In one sentence:** one loss only halves the window instead of resetting it.
Worked example: cwnd 20, one loss → ssthresh 10, cwnd 13, inflates 14 … 29 while
duplicate ACKs arrive, deflates to 10 at the new ACK.
**Weakness:** Reno leaves fast recovery at the **first new ACK, even a partial one**
(an ACK that covers the first hole but not the rest of the window). With 2 or more
losses in one window, the next hole can only be found by 3 *new* duplicate ACKs.
Then ssthresh is halved again (10.5 → 5.25 in the tests). Often there are too few
packets in flight to produce those duplicate ACKs, and Reno waits for a
**timeout**: 1 timeout in S2 with 3 and with 4 losses.

### TCP New Reno (`simulator/newreno.py`, RFC 6582)

Reno with a fix for multiple losses in one window.

| Event | What New Reno does |
|---|---|
| 3rd duplicate ACK | as Reno, **and remember `recover` = highest segment sent so far** |
| more duplicate ACKs | `cwnd += 1` (as Reno) |
| **partial ACK** (new data ACKed, but below `recover`) | the next hole is lost too: **resend it at once**, `cwnd = cwnd − newly ACKed + 1`, **stay in fast recovery** |
| **full ACK** (covers `recover`) | `cwnd = ssthresh`, leave fast recovery |
| timeout | `cwnd = 1`, slow start |

**In one sentence:** it repairs **one hole per round-trip time** without leaving
fast recovery, halving ssthresh only **once** per window of losses.
**Result:** 0 timeouts and no spurious resends in all S2 variants.
**Weakness:** with many holes (e.g. 150 after a slow-start overshoot) "one per
RTT" takes a long time, and without SACK nothing faster is possible.

A guard shared by all three: a new fast retransmit is only allowed when
`snd_una > recover`. Duplicate ACKs caused by data resent *before* the last loss
event cannot start another one. This stops Tahoe's go-back-N resends from
triggering a chain of false fast retransmits.

### Side by side

| | Tahoe | Reno | New Reno |
|---|---|---|---|
| cwnd after 3 dup ACKs | 1 | ssthresh + 3 | ssthresh + 3 |
| fast recovery | no | yes, leaves at first new ACK | yes, leaves at full ACK only |
| several losses in one window | slow start + resend all | halves again or times out | one hole per RTT |
| spurious resends | many (go-back-N) | few | none in S2 |
| in Linux? | no | no (Linux "reno" without SACK = New Reno) | yes, as `linux_reno` |

### What Linux "reno" actually is

Linux's `reno` module (`tcp_congestion_control=reno`) only sets the growth rules
(slow start, +1 per RTT, `ssthresh = max(cwnd/2, 2)`). **Loss recovery is done by
the TCP core**. With SACK off, the core uses New Reno style partial-ACK recovery
(RFC 6582), so it does **not** leave recovery at a partial ACK like classic Reno.
It also reduces cwnd gradually during recovery (**PRR**, RFC 6937) instead of
inflating it. Tahoe does not exist in Linux at all.

To make Linux as "textbook" as possible, every Mininet host gets (`host_setup.py`):
reno, **SACK and DSACK off**, no Tail Loss Probe, no RACK, no F-RTO, no ECN, no
cached metrics, TSO/GSO/GRO offloads off, and `initcwnd 1`.

---

## Scenarios and how to run each one

One definition (`simulator/scenarios.py`) feeds both parts. Defaults:
10 Mbit/s bottleneck, 20 ms one-way delay (base RTT 40 ms), drop-tail queue of
100 packets, 20 s, 1460-byte segments, initial ssthresh 32 in the simulator.

| ID | What it tests | Variants | Simulator | Mininet |
|---|---|---|---|---|
| **S1** | single loss | segment 300 dropped once (large queue: no other loss) | yes | no (netem cannot drop a chosen segment) |
| **S2** | several losses in **one** window | 2, 3 or 4 drops at 300, 303, 306, 309 | yes | no |
| **S3** | random loss | 0.1 %, 1 %, 5 % | 5 seeds | 3 runs |
| **S4** | more traffic | 1, 2, 4 flows (started 2 s apart); 4 flows + UDP ramp 2→4→6 Mbit/s | yes | 3 runs |
| **S5** | variable bandwidth | 10 → 2 Mbit/s at 10 s → 10 Mbit/s at 20 s, queue 50, 30 s | yes | 3 runs |
| **S6** | different delays | base RTT 10, 50, 200 ms, 0.5 % loss | 5 seeds | 3 runs |
| **S6Q** | check for S6: queue or delay? | RTT 50 ms with queue 25 / 100 / 400, and once without loss | 5 seeds | 3 runs |

```bash
# Simulator (any scenario, any algorithms)
.venv/bin/python -m tcp_lab.run_sim_scenarios --scenario S2
.venv/bin/python -m tcp_lab.run_sim_scenarios --scenario S3 --algorithms reno,newreno --seeds 10
.venv/bin/python -m tcp_lab.run_sim_scenarios --scenario S5 --no-plots

# Mininet (S3, S4, S5, S6, S6Q; root needed, run on the Mininet machine)
scripts/run_tcp_lab_mininet.sh --scenario S3
scripts/run_tcp_lab_mininet.sh --scenario S4 --variant 2_flows --runs 5
scripts/run_tcp_lab_mininet.sh --scenario S6 --controller ryu   # switches under Ryu

# After either: refresh the statistics and the report
.venv/bin/python -m tcp_lab.run_analysis
```

Simulator output, per variant in `results/<S>/<variant>/`:
- `sim_<algorithm>_events.csv`: every event;
- the plots `cwnd.png`, `sequence.png` (plus `sequence_zoom.png` for S1/S2), `rtt.png` and `throughput.png`;
- `timeseries.json`, the data for the dashboard.

`results/<S>/summary.json` holds the table: `results` for seed 1, `seed_results` for every seed, and `linux_start_results` (see the validation section).

Mininet output: `results/<S>/mininet_summary.json` (one row per run) and
`results/<S>/<variant>/mininet_run<N>/`, which holds the iperf3 reports, ss CSVs,
pcaps, the time-sequence CSVs and `run.json`.

---

## What is measured

| Metric | Definition |
|---|---|
| **goodput** | new, in-order data delivered to the application per second (excludes resends) |
| **throughput** | all data that reached the receiver per second, **resends included** |
| **retransmissions** | segments sent more than once |
| needed / **spurious** | a resend is spurious if the receiver **already had** those bytes, otherwise needed |
| **timeouts**, fast retransmits | how losses were detected |
| **recovery time** | from the first resend after a loss until everything sent before it is ACKed |
| **RTT** (avg, P95) | simulator: every ACK; Mininet: the kernel's smoothed RTT from `ss` every 50 ms |
| **Jain fairness** | `(Σx)² / (n·Σx²)` over per-flow goodput: 1 = equal shares, 1/n = one flow takes all |
| **packet loss rate** | drops at the bottleneck / packets offered to it |

Totals for several flows divide **total bytes by the total run time**. Adding up
per-flow rates would be wrong when flows start at different times.

---

## Results and recommendation

These are the numbers from the full run (simulator 5 seeds, Mininet 3 runs). The
source of truth is `results/analysis/report.md`, which `run_analysis` rewrites
from whatever is in `results/`.

**Recommendation: New Reno** (simulator). It scored 106 points against Reno's 64
and Tahoe's 53, and won all of S2–S6. S1 was a tie with Reno. Points count only
**clear** wins (see [Analysis method](#analysis-method)).

| Scenario | Simulator finding | Mininet (Linux reno) |
|---|---|---|
| S1 one loss | Reno = New Reno 8.84 Mbit/s; Tahoe 8.52 (back to cwnd 1); recovery 43 ms (1 RTT) for all | – |
| S2 several losses | 3 losses: New Reno 8.75, Tahoe 8.42, **Reno 6.91 with a timeout**; Tahoe 3 spurious resends of 6 | – |
| S3 random loss | New Reno best at every rate; at 5 % Reno is **worst** (24.6 timeouts, Tahoe 13.2) | 1 %: 3.44 vs New Reno 3.19 (sim) |
| S4 more flows | all fill the link (~9.6); with 4 flows New Reno resends least (43 vs 53 / 68) but is least fair (Jain 0.87 vs 0.89 / 0.91) | 7.0–7.9: first slow start overshoots the queue |
| S5 bandwidth step | New Reno 7.06, 0 timeouts, fewest resends; longest recoveries (one hole per RTT) | 6.21 |
| S6 delay | 9.45 → 3.83 → 0.92 Mbit/s (New Reno) for 10 → 50 → 200 ms | 9.09 → 3.46 → 1.28 |
| S6Q queue check | goodput 3.83 for queue 25, 100 **and** 400; 9.57 without loss | 3.79 / 3.84 / 4.21; 5.85 without loss |

**Why S6 drops from 9 to 3 Mbit/s:** because of the delay together with the
0.5 % loss, not the queue. At random loss p, a Reno-style flow keeps on average
only about `C/√p` segments in flight (Mathis formula): about 17 here, or 12 with
Linux's delayed ACKs, whatever the RTT. At 10 ms the link needs only about 9
segments (the bandwidth-delay product, BDP), so it stays full. At 50 ms it needs
43, so goodput falls to about `window × MSS / RTT`. S6Q proves it: changing the
queue 16-fold does not change the simulator's goodput, and removing the loss
restores the link rate.

**Does the simulator match Linux?** On goodput, once both start the same way,
Linux is closer to New Reno than to Reno in **12 of 15** variants, and within 5 %
of New Reno in 7. On timeouts, Linux had **more than both** simulated algorithms
in 9 of 15 variants. That gap is reported, not hidden.

---

## Limitations

1. **No Tahoe in Linux.** Tahoe numbers come only from the simulator.
2. **No classic Reno in Linux either.** With SACK off, Linux recovers like New
   Reno (partial ACKs keep it in recovery) and uses PRR. Mininet is therefore a
   check of **New Reno-style** behaviour and of the simulator, not a three-way
   comparison.
3. **SACK is off on purpose.** With SACK (the Linux default) the sender knows
   exactly which segments are missing and repairs several holes per RTT, so the
   differences between Tahoe, Reno and New Reno would disappear. This is also why
   the Linux runs repair 150+ holes "one per RTT" after an overshoot, which a
   modern SACK stack would fix in about one RTT.
4. **Simulator vs Mininet gap.** The known causes, largest first:
   - **Initial ssthresh.** Our scenarios start with ssthresh 32, but Linux has no
     limit. On a clean link the first Linux slow start overshoots far past
     BDP + queue (max cwnd 273 vs about 143 that fit at 50 ms), loses a burst
     from the queue, and needs seconds to repair it. This alone explained most of
     the early gap (S4 1_flow: Linux 7.0 vs simulator 9.6; simulator with a
     Linux-like start 7.4). The analysis compares Linux with **Linux-like-start**
     simulator runs.
   - **Delayed ACKs.** Linux ACKs every second segment, so cwnd grows more slowly
     and fewer duplicate ACKs come back. The simulator ACKs every segment.
   - **Recovery details.** PRR instead of inflation; a different RTO estimator in
     detail. Linux had more timeouts than both simulated algorithms in 9 of 15
     variants, and why is not fully settled by these results.
   - **Segment size**: 1448 bytes in Linux (timestamp option), 1460 in the simulator.
   - **Few runs.** 3 Mininet runs per variant, so their means are uncertain (look
     at the min–max).
5. **Simulator simplifications:**
   - it counts segments, not bytes;
   - there are no delayed ACKs;
   - the ACK path has no queue and no loss;
   - there is one bottleneck and no cross-traffic except the UDP sources.
   - A duplicate ACK caused by a *resent* segment is ignored. This follows the idea of RFC 6582's timestamp heuristic.
6. **Mininet cannot run S1/S2** (netem cannot drop one chosen segment), and 20 s
   is only 100 RTTs at 200 ms, so the start phase weighs a lot there.
7. **"Live" on the dashboard is a playback.** The simulator finishes a run in
   under a second, so it runs first and is then played back at the chosen speed.
   Mininet runs need root and are replayed from their recorded `ss` samples.

---

## Mininet details

All code in `tcp_lab/mininet/` uses only the Python standard library, so it runs
under `sudo python3` with the system Python that has Mininet.
**Needs:** Mininet, Open vSwitch, `iperf3`, `tcpdump`, `ethtool`, `iproute2` (`tc`, `ss`, `nstat`).

### Topology (dumbbell)

```
c1 10.0.0.11 --\                                   /-- sv1 10.0.0.21
c2 10.0.0.12 ---- sw1 ==== bottleneck (TCLink) ==== sw2
c3 10.0.0.13 --/  eth1                         eth1 \-- sv2 10.0.0.22
```

- `tc` on `sw1-eth1` (data direction) holds a `netem` root (delay and random or
  burst loss) with a `tbf` child (bandwidth and a drop-tail queue in bytes). It is
  changed at runtime with `tc qdisc replace`.
- `sw2-eth1` (the ACK direction) gets the same delay, with no shaping and no loss.
- Run *N* uses `netem seed N`, so its random-loss pattern can be repeated.
- Switches are named `sw1`/`sw2`, not `s1`, so the dashboard API, which checks for
  a bridge called `s1`, does not mistake the lab for the load-balancer network.
- OVS works as a learning switch by default; `--controller ryu` puts the switches
  under the project's Ryu controller instead.
- **VIP mode** (smoke test only) uses the project's load-balancer topology: stop
  `run_mininet.sh`, and keep Ryu running.
  - iperf3 cannot go through the VIP: its control and data connections use
    different source ports and may reach different backends.
  - `bulk_tcp.py` uses a single connection instead.

### Smoke test

```bash
scripts/run_tcp_lab_smoke.sh                    # dumbbell, OVS as a learning switch
scripts/run_tcp_lab_smoke.sh --controller ryu   # switches under Ryu on :6653
scripts/run_tcp_lab_smoke.sh --target vip       # client -> VIP 10.0.0.100 through the LB
```

One 20 s Linux reno flow, with the bandwidth stepping from 10 to 3 Mbit/s half way.
It prints PASS/FAIL checks, including "started with cwnd 1", and the
retransmission count from iperf3, nstat, ss and pcap, which must agree.

### Where each Mininet number comes from

| Number | Source |
|---|---|
| goodput | iperf3 servers: bytes the application read / experiment length |
| throughput | pcap **at the server**: payload bytes that arrived, resends included |
| retransmissions | iperf3 (sender kernel); nstat and the sender pcap as cross-checks |
| spurious / needed | pcap at the server: a resend whose bytes the receiver had **already ACKed** is spurious |
| timeouts, fast retransmits, recoveries | nstat on the clients |
| queue drops / random drops | `tc -s`: tbf drops = queue full; netem − tbf = random loss |
| RTT, cwnd, ssthresh | `ss -tin` every 50 ms (the kernel's smoothed RTT) |

### Problems found and fixed while building it

- **initcwnd 1 did not apply at first.** Mininet runs host commands on a
  terminal, where iproute2 **colours** `ip route show`. The colour codes broke the
  `ip route change` command, and nothing reported it. Routes are now read through
  a pipe (`ip route show | cat`) and checked afterwards.
- **"first cwnd 10" was a measuring mistake.** That ss sample was taken during the
  handshake (`SYN-SENT`), where Linux shows its default of 10. The sampler now
  records the TCP state, and the runner works out the initial cwnd from the first
  established sample. In slow start Linux adds one segment per segment ACKed, so
  `initial cwnd = cwnd − (delivered − 1)`. If it is not 1, or any host setting is
  wrong, the runner **stops** and stores nothing.
- **`mn -c` was too blunt.** Mininet's cleanup calls the obsolete `egrep`, removes
  every OVS bridge and kills every `ryu-manager`. The lab's `cleanup.py` uses
  `grep -E` and only touches the lab's own nodes.

---

## Analysis method

```bash
.venv/bin/python -m tcp_lab.run_analysis     # results/analysis/report.md, analysis.json, *.png
```

- **Never ranked on one run.** Every metric is reported as mean (median, min–max,
  n). The median is there because one bad run can pull the mean a long way (S6
  rtt_10ms on Mininet: 80, 198 and 786 retransmissions, so mean 355, median 198).
- **Seeds.** Random-loss variants (S3, S6, S6Q) run with seeds 1–5. The others
  have no randomness and run once.
- **Scoring (simulator only).** For every variant and metric, algorithm A gets
  `weight` points for each algorithm it **clearly** beats: its mean must be better
  by more than `max(std A, std B, 2 % of the larger mean)`. So noise cannot decide
  a ranking, and 9.45 vs 9.44 is a tie.
  - Weights: goodput 3, timeouts 2, recovery time 2, spurious resends 1,
    retransmissions 1, P95 RTT 1, fairness 1 (several flows only).
  - The most points over S1–S6 is the recommendation.
- **Validation.** Linux is compared with simulator runs of Reno and New Reno that
  **start like Linux** (no ssthresh limit), so like is compared with like. The
  analysis reports which simulated algorithm is closer on goodput, and whether
  Linux had more, fewer or in-between timeouts.
- **Mathis formula** (`compare.py`): `rate = MSS/RTT × C/√p`, with `C = 1.22`
  (an ACK per segment) or `0.87` (delayed ACKs), capped at the link rate. It is
  used to explain S6, and its numbers are labelled "model".

---

## API and dashboard

FastAPI router `api/tcp_lab/` (registered in `api/main.py`):

| Endpoint | Returns |
|---|---|
| `GET /api/tcp-lab/scenarios` | scenarios, variants, which results exist |
| `GET /api/tcp-lab/results/{S}` | simulator and Mininet summaries (labelled) |
| `GET /api/tcp-lab/results/{S}/{variant}/timeseries?run=1` | simulator series (seed 1) and the cwnd of one Mininet run |
| `GET /api/tcp-lab/analysis` | `analysis.json` |
| `GET /api/tcp-lab/analysis/plots[/{name}]` | analysis PNGs |
| `POST /api/tcp-lab/live/simulate` | `{scenario, variant, algorithms, seed, speed}`: run the simulator and stream it |
| `POST /api/tcp-lab/live/replay` | `{scenario, variant, run, speed}`: stream a recorded Mininet run |
| `GET /api/tcp-lab/live`, `POST /api/tcp-lab/live/stop` | status / stop |

WebSocket messages on the existing `/ws/events`:

- `TCP_LAB_RUN_STARTED`
- `TCP_CWND_SAMPLE`: time, algorithm, flow, cwnd, ssthresh, state
- `TCP_LOSS_EVENT`
- `TCP_LAB_RUN_FINISHED`, which carries that run's numbers
- `TCP_LAB_RUN_STOPPED`

Every message has `run_id` and `source`.

Safety and size: URL names are checked against the scenario definitions before any
file is opened, so a request cannot read outside `results/`. The API never imports
matplotlib, so the Docker image needs nothing new.

The **TCP Lab** tab (`front-end/src/components/tcplab/`) shows:
- the live cwnd chart, with solid cwnd, dashed ssthresh, ▲ fast retransmit and ✕ timeout;
- the results table, with mean (median, min–max, n) per algorithm and a source label on each column;
- the recommendation, the simulator-vs-Linux table and the analysis plots.

It only displays what the API returns.

---

## Files

| Path | Job |
|---|---|
| `simulator/base.py` | states, slow start / congestion avoidance growth, the ssthresh rule, timeout |
| `simulator/tahoe.py`, `reno.py`, `newreno.py` | what each algorithm does on ACK / dup ACK |
| `simulator/rto.py` | RFC 6298 retransmission timer |
| `simulator/tcp_sim.py` | event loop, bottleneck link, sender, receiver, UDP sources |
| `simulator/scenarios.py` | S1–S6, S6Q |
| `run_sim_scenarios.py` | runs the simulator, seeds, plots, `summary.json` |
| `mininet/hosts.py`, `dumbbell_topo.py` | topology |
| `mininet/host_setup.py` | sysctls, offloads, initcwnd |
| `mininet/tc_controller.py` | netem + tbf commands |
| `mininet/traffic.py`, `bulk_tcp.py` | iperf3 / tcpdump / nstat; single-connection sender |
| `mininet/ss_sampler.py`, `pcap_parser.py` | kernel state every 50 ms; pure-Python pcap reader |
| `mininet/scenarios.py` | S3–S6, S6Q as Mininet plans |
| `mininet/cleanup.py`, `smoke_test.py` | leftovers cleanup; end-to-end check |
| `run_mininet_scenarios.py` | runs the plans N times, checks initial cwnd |
| `analysis/metrics.py` | goodput, spurious, recovery time, Jain, time series |
| `analysis/plots.py` | matplotlib (Agg) plots |
| `analysis/stats.py`, `scoring.py`, `compare.py`, `report.py` | Phase 5 |
| `run_analysis.py` | runs the analysis |
| `../api/tcp_lab/` | API |
| `../front-end/src/components/tcplab/` | dashboard page |
| `../tests/test_tcp_sim.py`, `test_tcp_lab_*.py` | tests (real captured tool output in `tests/data/tcp_lab/`) |

`tcp_lab/ruff.toml` switches off a few "write it more compactly" lint rules for
this folder only. The code is deliberately written with plain loops and if/else
so that every step can be explained.
