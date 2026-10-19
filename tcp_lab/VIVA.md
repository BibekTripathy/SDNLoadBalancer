# TCP Lab - likely viva questions

Short answers, each backed by our own results where possible. Numbers are means
from the full run (simulator: 5 seeds for random loss; Mininet: 3 runs per
variant) and say whether they come from the **simulator** or from **Mininet**
(real Linux reno, SACK off). `results/analysis/report.md` has every table.

## The algorithms we implemented

### 1. What is cwnd, and how is it different from the receiver window?
cwnd is the sender's own limit on unacknowledged data, set by **congestion
control** to protect the network. The receiver window (rwnd) is the receiver's
limit, set by **flow control** to protect its buffer. The sender may have
`min(cwnd, rwnd)` in flight. In our runs rwnd is large (1000 segments), so cwnd
is always the limit.

### 2. Slow start doubles cwnd every RTT. Why is it called "slow"?
Because it starts from **1 segment** instead of sending a whole window at once,
which is what TCP did before 1988. cwnd grows by 1 per ACK, which doubles it per
RTT, until it reaches ssthresh. After that, congestion avoidance adds only about
1 segment per RTT.

### 3. Why wait for 3 duplicate ACKs instead of 1?
One or two duplicate ACKs can be caused by **reordering**: a segment arrives late,
not lost. Three in a row is the usual threshold (RFC 5681) for "this segment is
probably lost". The code checks `dupack_count == DUPACK_THRESHOLD`.

### 4. Tahoe, Reno, New Reno: the difference in one line each?
- **Tahoe:** every loss → cwnd = 1, slow start, resend everything from the hole (go-back-N).
- **Reno:** 3 duplicate ACKs → cwnd = ssthresh + 3, fast recovery, leaves it at the **first** new ACK.
- **New Reno:** like Reno, but it stays in fast recovery until **everything** sent
  before the loss is ACKed, and resends the next hole at each **partial ACK**.

### 5. What is a partial ACK, and why does it matter?
After a fast retransmit, the next new ACK may cover the resent segment but not
everything that was in flight (`ack < recover`). That means another segment from
the same window is also lost.
- **Reno** treats any new ACK as "done", leaves fast recovery and must find the
  next hole again with 3 new duplicate ACKs, or with a timeout.
- **New Reno** resends that hole at once.

Simulator, S2 with 3 losses: Reno 6.91 Mbit/s with 1 timeout; New Reno 8.75
Mbit/s with 0 timeouts.

### 6. Why does Reno set cwnd = ssthresh + 3, and then add 1 per duplicate ACK?
Each duplicate ACK means one segment **left the network** (it reached the
receiver). The 3 that triggered fast retransmit account for the "+3". Every
further one "inflates" cwnd by 1, which lets one new segment out, so data keeps
flowing during recovery. At the new ACK, cwnd is "deflated" back to ssthresh.
Worked example from our tests: cwnd 20 → ssthresh 10, cwnd 13, 14 … 29 during
recovery, then 10.

### 7. When exactly is ssthresh halved?
At exactly two moments, using `ssthresh = max(window/2, 2)`:
- at the 3rd duplicate ACK, when not already in fast recovery (window = cwnd);
- at a timeout (window = cwnd, or **ssthresh** when the timeout happens *inside*
  fast recovery, because cwnd is inflated there).

Duplicate ACKs and partial ACKs inside fast recovery never change ssthresh.
Consequence: Reno with two losses in one window halves **twice** (10.5 → 5.25 in
the tests); New Reno halves **once**.

### 8. How is the retransmission timeout computed?
RFC 6298 (`rto.py`):
- `SRTT = 7/8·SRTT + 1/8·sample`
- `RTTVAR = 3/4·RTTVAR + 1/4·|SRTT − sample|`
- `RTO = SRTT + 4·RTTVAR`

The minimum is 200 ms and the start value 1 s. The RTO doubles after each timeout
(exponential backoff) and is recomputed from the next sample. Our ACKs echo the
send time of the segment that caused them (like TCP timestamps), so even resent
segments give a correct RTT sample.

### 9. Why did you turn SACK off?
With SACK the receiver reports exactly which blocks it has, so the sender can
repair several holes in one RTT. All three algorithms would then look much the
same, and Tahoe vs Reno vs New Reno would not show. SACK off gives the textbook
"one hole per RTT" behaviour the assignment is about. The price is that Linux
needs seconds to repair a burst of losses (see question 15).

### 10. Why are there no Tahoe results from Mininet?
Linux has no Tahoe. Linux "reno" only sets the growth rules. Loss recovery is done
by the TCP core, which without SACK behaves like **New Reno** (and uses PRR, not
inflation). So Mininet gives one real algorithm, labelled `linux_reno`. The
three-way comparison comes from the simulator, and Mininet checks that the
simulator behaves like real TCP.

## Our results

### 11. Which algorithm do you recommend, and how do you know it is not just luck?
**New Reno** (simulator): 106 points against Reno 64 and Tahoe 53, best in S2–S6,
and tied with Reno in S1. Points count only **clear** wins: the mean over seeds
must be better by more than the larger standard deviation and by at least 2 %. A
difference smaller than the run-to-run noise scores nothing, and nothing is
ranked on one run.

### 12. In S2, why does Reno time out with 3 losses but not with 2?
Simulator. With 2 losses Reno halves twice (two fast recoveries) and gets by:
0 timeouts, 8.05 Mbit/s. With 3 losses, after two halvings the window is small
(ssthresh about 5 in the trace), most likely too small for enough segments to be in
flight to produce 3 new duplicate ACKs for the third hole. Reno has to wait for the
timer: 1 timeout, recovery 0.35 s instead of 0.12 s, 6.91 Mbit/s. New Reno repairs
the holes one per RTT, in 0.08–0.16 s for 2–4 losses, with no timeout.

### 13. Why does Tahoe have spurious retransmissions?
After the loss, Tahoe goes back to the hole and resends **everything** after it.
The receiver already had most of those segments. Simulator, S2: Tahoe resends 3,
6 and 10 segments for 2, 3 and 4 losses, of which 1, 3 and 6 were spurious. Reno
and New Reno resend only the missing ones (New Reno: 0 spurious). We count
spurious resends at the **receiver**: a segment it already had.

### 14. At 5 % loss, why is Reno worse than Tahoe?
Simulator, S3 5 %: Reno 0.89 Mbit/s with 24.6 timeouts; Tahoe 0.99 with 13.2;
New Reno 1.11 with 13.2. At 5 % loss, several losses in one window are common.
Reno leaves fast recovery at the partial ACK and then often has to wait for a
timeout of at least 200 ms. Tahoe does not wait: it restarts slow start straight
away. New Reno avoids both problems.

### 15. On Mininet, why did 0.1 % loss give more retransmissions than 1 %?
Mininet, S3: 166 retransmissions at 0.1 % against 58 at 1 %. Of the 0.1 % drops,
only about 15 per run were random; about 152 were **queue drops**. With so little
random loss, the first slow start is not stopped early, and Linux has no initial
ssthresh. cwnd doubles far past what the path holds (BDP about 34 + queue 100 packets),
and a whole burst is dropped from the full queue. Without SACK, those holes are
repaired one per RTT, which takes seconds. At 1 % a random loss hits early in slow
start, the queue never overflows (0 queue drops), and every loss is a single,
cheap fast retransmit. Goodput is still higher at 0.1 % (6.12 vs 3.44 Mbit/s).

### 16. Why does goodput fall from about 9 to 3 Mbit/s when the RTT goes from 10 to 50 ms (S6)? Is it the queue?
It is the delay together with the 0.5 % loss, **not** the queue.
- Each loss halves the window, and it grows back by 1 per RTT. So at loss rate p a
  Reno-style flow keeps on average only about `C/√p` segments in flight (the
  Mathis formula): about 17 here, or 12 with Linux's delayed ACKs, whatever the RTT.
- At 10 ms the link needs only about 9 segments to stay full (the bandwidth-delay
  product), so it stays full: 9.45 Mbit/s (simulator), 9.09 (Mininet).
- At 50 ms it needs 43, so goodput is about `window × MSS / RTT`. The formula
  predicts 4.05 / 2.84 Mbit/s; the simulator measured 3.83 and Mininet 3.46.

Proof that the queue is not the cause, scenario S6Q:
- **Simulator:** goodput is 3.83 Mbit/s with queues of 25, 100 and 400 packets;
  without random loss it is 9.57.
- **Mininet:** 3.79 / 3.84 / 4.21. The only effect of the bigger queue was that the
  first slow-start overshoot fitted into it (0 queue drops with 400 packets).

### 17. Why is real Linux slower than your simulator on a clean link?
S4 with 1 flow and no random loss: Mininet 7.01 Mbit/s, simulator 9.64. Our
scenarios start the simulator at ssthresh 32, but Linux starts with no limit, so
its first slow start overshoots and loses a burst from the queue (159 queue
drops). When the simulator's New Reno is started the same way, it gets 7.37 Mbit/s,
close to Linux. So most of the gap was the starting condition, not the algorithm.
The analysis therefore compares Linux with "Linux-like start" simulator runs.

### 18. Does the simulator match real Linux, then?
On goodput, with the same start, Linux is closer to New Reno than to Reno in
12 of 15 variants, and within 5 % of it in 7. On timeouts it does not match well:
Linux had more timeouts than both simulated algorithms in 9 of 15 variants. In
those runs we also see spurious resends, which is what a timeout without SACK
produces: Linux resends everything unacknowledged. Why Linux reaches a timeout
more often (its RTO and recovery details differ from ours) is not settled by our
results, and with 3 runs some of it may be noise. Other known differences:
- Linux delays ACKs;
- it reduces cwnd gradually during recovery (PRR);
- its segments are 1448 bytes, not 1460.

### 19. S5: New Reno has the longest recovery time but the best goodput. How?
Simulator, bandwidth 10 → 2 → 10 Mbit/s: New Reno's average recovery is 0.69 s
(Tahoe 0.22, Reno 0.31), but it has the most goodput (7.06), 0 timeouts and the
fewest resends (25 vs 44 / 47, 0 spurious). When the bandwidth drops, many packets
are lost from the queue at once. New Reno stays in fast recovery and repairs them
one per RTT, which takes long but keeps data flowing and never drops cwnd to 1.
Reno timed out once; Tahoe went back to cwnd 1 and resent 24 segments the
receiver already had.

### 20. Why is fairness below 1 in S4, and why is New Reno the least fair with 4 flows?
The flows start 2 s apart, so each one meets a different queue. Jain's index with
4 flows (simulator): Tahoe 0.91, Reno 0.89, New Reno 0.87. Linux on Mininet was
lower and varied more (0.70, ranging from 0.53 to 0.91 over 3 runs). S4 has no
random loss, so the simulator result is a single deterministic run per algorithm.
The New Reno vs Tahoe difference is small and we did not investigate its cause, so
we would not draw a strong conclusion from it.

### 21. What is the difference between goodput and throughput in your tables?
Throughput counts everything that reached the receiver, **resends included**.
Goodput counts only new, in-order data delivered to the application. The gap is
wasted capacity: for example Mininet S4 with 4 flows, 7.99 vs 7.60 Mbit/s.

### 22. Why do you show the median as well as the mean?
Real runs vary a lot. Mininet S6 at 10 ms gave 80, 198 and 786 retransmissions:
the mean (355) is pulled up by one run with a long loss episode, while the median
(198) is not. Showing mean, median and min–max makes that visible.

### 23. How do you know the Mininet numbers are right?
- **Four counts agree.** iperf3, the kernel counters (nstat), `ss` and our own pcap
  parser count the same retransmissions (e.g. 130 in the smoke test).
- **Initial cwnd is checked.** Every run checks that each connection started with
  cwnd 1, and the runner stops otherwise. That check found two real problems: the
  coloured output of `ip`, and a sample taken during the handshake.
- **Parsers are tested on real data.** The parsers are unit-tested on real
  captured tool output, and the pcap parser on a hand-built capture.

### 24. What would change with SACK, or with CUBIC?
- **SACK:** the sender learns all holes at once and repairs several per RTT. The
  long Linux recoveries after an overshoot (2+ s in S4) would mostly disappear, and
  New Reno's advantage over Reno would shrink.
- **CUBIC** (the Linux default): grows the window as a cubic function of the time
  since the last loss, not +1 per RTT. It refills large BDPs much faster, so S6 at
  200 ms would improve. It still cuts the window at every random loss, so the
  loss-limited behaviour remains.

We did not run either. They are outside the assignment, which is about the classic
loss-based algorithms.
