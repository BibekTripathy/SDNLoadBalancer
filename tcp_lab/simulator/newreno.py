"""
TCP New Reno (RFC 6582).

Same as Reno, except for what happens on a new ACK during fast recovery:
  - On entering fast recovery we remember recover = highest sequence sent.
  - PARTIAL ACK (acknowledges new data but not up to "recover"):
    another segment from the same window was lost. Retransmit it at once
    (the segment at the new snd_una), deflate cwnd by the amount of data
    just acknowledged, add back 1, and STAY in fast recovery.
  - FULL ACK (acknowledges everything up to "recover"):
    cwnd = ssthresh, leave fast recovery -> congestion avoidance.

Result: n losses in one window are repaired in about n RTTs with no
retransmission timeout. Linux "reno" with SACK disabled behaves this way.
"""

from tcp_lab.simulator.base import (
    ACTION_NONE,
    ACTION_RETRANSMIT,
    CONG_AVOID,
    DUPACK_THRESHOLD,
    FAST_RECOVERY,
    CongestionControlBase,
)


class NewRenoSender(CongestionControlBase):
    name = "newreno"

    def __init__(self, initial_cwnd=1, initial_ssthresh=64):
        super().__init__(initial_cwnd, initial_ssthresh)
        self.partial_acks = 0

    def on_ack(self, ack_no, newly_acked):
        if self.state == FAST_RECOVERY:
            if ack_no > self.recover:
                # FULL ACK: every segment of the lossy window is now acked.
                # Deflate to ssthresh, leave fast recovery.
                self.cwnd = self.ssthresh
                self.state = CONG_AVOID
                return ACTION_NONE

            # PARTIAL ACK: the next hole is at ack_no -> retransmit it now
            # and stay in fast recovery. Deflate by what was acked, add 1.
            self.partial_acks += 1
            self.cwnd = self.cwnd - newly_acked + 1.0
            if self.cwnd < 1.0:
                self.cwnd = 1.0
            return ACTION_RETRANSMIT

        # Normal new ACK: slow start or congestion avoidance growth
        self.grow_window()
        return ACTION_NONE

    def on_dupack(self, dupack_count, snd_una, highest_sent):
        if self.state == FAST_RECOVERY:
            # Extra dup ACK in fast recovery -> inflate cwnd by 1 segment
            self.cwnd = self.cwnd + 1.0
            return ACTION_NONE

        if dupack_count != DUPACK_THRESHOLD:
            return ACTION_NONE

        if not self.can_start_fast_retransmit(snd_una):
            # This hole belongs to a window we already recovered (RFC 6582 sec 3.2 step 1)
            return ACTION_NONE

        # 3 dup ACKs -> fast retransmit + enter fast recovery, remember "recover"
        self.fast_retransmits += 1
        self.ssthresh = self.half_window()
        self.cwnd = self.ssthresh + 3.0
        self.state = FAST_RECOVERY
        self.recover = highest_sent
        return ACTION_RETRANSMIT
