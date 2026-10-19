"""
TCP Reno (4.3BSD-Reno, RFC 5681).

Adds FAST RECOVERY to Tahoe:
  - 3 dup ACKs -> fast retransmit the missing segment,
    ssthresh = cwnd/2, cwnd = ssthresh + 3 (the 3 segments that
    left the network and caused the dup ACKs), enter FAST_RECOVERY.
  - Each further dup ACK -> cwnd += 1 ("inflate"), because one more
    segment has left the network. This lets new data flow during recovery.
  - The first ACK of new data -> cwnd = ssthresh ("deflate"), leave
    fast recovery, continue in congestion avoidance.

Weakness: Reno leaves fast recovery on the FIRST new ACK, even if it is
only a partial ACK (more holes are still missing in the same window).
With 2+ losses in one window the next hole usually cannot collect 3 new
dup ACKs, so Reno ends up waiting for a retransmission timeout.
"""

from tcp_lab.simulator.base import (
    ACTION_NONE,
    ACTION_RETRANSMIT,
    CONG_AVOID,
    DUPACK_THRESHOLD,
    FAST_RECOVERY,
    CongestionControlBase,
)


class RenoSender(CongestionControlBase):
    name = "reno"

    def on_ack(self, ack_no, newly_acked):
        if self.state == FAST_RECOVERY:
            # New ACK during fast recovery -> deflate cwnd to ssthresh and
            # leave fast recovery (even if this is only a partial ACK).
            self.cwnd = self.ssthresh
            self.state = CONG_AVOID
            return ACTION_NONE

        # Normal new ACK: slow start or congestion avoidance growth
        self.grow_window()
        return ACTION_NONE

    def on_dupack(self, dupack_count, snd_una, highest_sent):
        if self.state == FAST_RECOVERY:
            # Extra dup ACK in fast recovery -> inflate cwnd by 1 segment
            self.cwnd = self.cwnd + 1.0
            return ACTION_NONE

        if dupack_count != DUPACK_THRESHOLD:
            # Fewer than 3 dup ACKs: could be reordering, do nothing yet
            return ACTION_NONE

        if not self.can_start_fast_retransmit(snd_una):
            # Leftover dup ACKs from data resent after a timeout
            return ACTION_NONE

        # 3 dup ACKs -> fast retransmit + enter fast recovery
        self.fast_retransmits += 1
        self.ssthresh = self.half_window()
        self.cwnd = self.ssthresh + 3.0
        self.state = FAST_RECOVERY
        return ACTION_RETRANSMIT
