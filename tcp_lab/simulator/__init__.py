"""
Pure-Python TCP congestion control simulator.

Files:
  base.py     - shared state (cwnd, ssthresh, state) + slow start / congestion avoidance growth
  tahoe.py    - TCP Tahoe
  reno.py     - TCP Reno
  newreno.py  - TCP New Reno (RFC 6582)
  rto.py      - retransmission timeout estimator (RFC 6298)
  tcp_sim.py  - the event-driven network: senders, bottleneck link, receivers
  scenarios.py - experiment definitions S1 - S6
"""

from tcp_lab.simulator.newreno import NewRenoSender
from tcp_lab.simulator.reno import RenoSender
from tcp_lab.simulator.tahoe import TahoeSender


def make_algorithm(name, initial_cwnd=1, initial_ssthresh=64):
    """Create a congestion control object from its name ('tahoe', 'reno', 'newreno')."""
    name = name.lower()
    if name == "tahoe":
        return TahoeSender(initial_cwnd, initial_ssthresh)
    if name == "reno":
        return RenoSender(initial_cwnd, initial_ssthresh)
    if name == "newreno":
        return NewRenoSender(initial_cwnd, initial_ssthresh)
    raise ValueError("Unknown algorithm: " + name)


ALGORITHMS = ["tahoe", "reno", "newreno"]
