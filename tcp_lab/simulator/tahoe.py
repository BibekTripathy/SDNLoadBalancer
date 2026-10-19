"""
TCP Tahoe (Jacobson 1988, 4.3BSD-Tahoe).

  - Slow start and congestion avoidance.
  - Fast retransmit on 3 duplicate ACKs, but NO fast recovery:
    every loss (3 dup ACKs or timeout) sets ssthresh = cwnd/2,
    cwnd = 1 and goes back to slow start.
  - After a loss we resend from the first unacknowledged segment
    (go-back-N). This is how the ns-2 Tahoe model used by Fall & Floyd
    (1996) behaves. It wastes some bandwidth on segments the receiver
    already has, but it repairs several losses in one window without
    waiting for a timeout.

Note: Linux does not ship a Tahoe implementation, so Tahoe results only
come from this simulator.
"""

from tcp_lab.simulator.base import (
    ACTION_GO_BACK_N,
    ACTION_NONE,
    DUPACK_THRESHOLD,
    SLOW_START,
    CongestionControlBase,
)


class TahoeSender(CongestionControlBase):
    name = "tahoe"

    def on_ack(self, ack_no, newly_acked):
        # A new ACK: grow the window (slow start or congestion avoidance)
        self.grow_window()
        return ACTION_NONE

    def on_dupack(self, dupack_count, snd_una, highest_sent):
        if dupack_count != DUPACK_THRESHOLD:
            # 1st/2nd dup ACK: maybe just reordering, wait.
            # 4th, 5th, ...: Tahoe has no fast recovery, so ignore them.
            return ACTION_NONE

        if not self.can_start_fast_retransmit(snd_una):
            # Dup ACKs caused by our own go-back-N resend - not a new loss
            return ACTION_NONE

        # 3 dup ACKs -> fast retransmit, then back to slow start with cwnd = 1
        self.fast_retransmits += 1
        self.ssthresh = self.half_window()
        self.cwnd = 1.0
        self.state = SLOW_START
        self.recover = highest_sent
        return ACTION_GO_BACK_N
