"""
Shared parts of the three congestion control algorithms.

Units: cwnd and ssthresh are measured in SEGMENTS (1 segment = 1 MSS),
sequence numbers are segment numbers (0, 1, 2, ...). This keeps every
number in the traces small enough to check by hand.

Every algorithm has the same interface, called by the sender in tcp_sim.py:

    on_ack(ack_no, newly_acked) -> action
    on_dupack(dupack_count, snd_una, highest_sent) -> action
    on_timeout(highest_sent)
    get_cwnd(), get_ssthresh(), get_state()

The "action" tells the sender what to do next:
    ACTION_NONE       - nothing special, just send what the window allows
    ACTION_RETRANSMIT - retransmit the first unacknowledged segment (snd_una)
    ACTION_GO_BACK_N  - resend everything starting from snd_una (Tahoe style)
"""

# The three TCP sender states we log and plot
SLOW_START = "SLOW_START"
CONG_AVOID = "CONG_AVOID"
FAST_RECOVERY = "FAST_RECOVERY"

# What the sender should do after an ACK event
ACTION_NONE = "NONE"
ACTION_RETRANSMIT = "RETRANSMIT"
ACTION_GO_BACK_N = "GO_BACK_N"

# Number of duplicate ACKs that triggers fast retransmit
DUPACK_THRESHOLD = 3

# ssthresh never goes below 2 segments (RFC 5681)
MIN_SSTHRESH = 2.0


class CongestionControlBase:
    name = "base"

    def __init__(self, initial_cwnd=1, initial_ssthresh=64):
        self.cwnd = float(initial_cwnd)
        self.ssthresh = float(initial_ssthresh)
        self.state = SLOW_START
        # "recover" = highest sequence number sent when the last loss
        # recovery started. Duplicate ACKs for data at or below this point
        # belong to the old loss event and must not start a new one.
        self.recover = -1
        self.fast_retransmits = 0
        self.timeouts = 0

    # ----- simple getters -------------------------------------------------
    def get_cwnd(self):
        return self.cwnd

    def get_ssthresh(self):
        return self.ssthresh

    def get_state(self):
        return self.state

    # ----- shared helpers -------------------------------------------------
    def update_state_from_window(self):
        """Outside fast recovery, the state only depends on cwnd vs ssthresh."""
        if self.cwnd < self.ssthresh:
            self.state = SLOW_START
        else:
            self.state = CONG_AVOID

    def grow_window(self):
        """Called once for every ACK that acknowledges new data (not in fast recovery)."""
        if self.cwnd < self.ssthresh:
            # Slow start: +1 segment per ACK -> cwnd doubles every RTT
            self.cwnd = self.cwnd + 1.0
        else:
            # Congestion avoidance: +1/cwnd per ACK -> about +1 segment per RTT
            self.cwnd = self.cwnd + 1.0 / self.cwnd
        # cwnd reaching ssthresh -> switch from SLOW_START to CONG_AVOID
        self.update_state_from_window()

    def half_window(self):
        """
        THE ssthresh RULE:  ssthresh = max(window / 2, 2)

        ssthresh changes at exactly two moments, nowhere else:
          1. 3rd duplicate ACK (fast retransmit), only when NOT already in
             fast recovery -> window is cwnd.
          2. Retransmission timeout -> window is cwnd, EXCEPT inside fast
             recovery, where cwnd is inflated by the dup ACKs and the real
             window is ssthresh, so the timeout halves ssthresh again.
        Extra dup ACKs and partial ACKs inside fast recovery never touch
        ssthresh; they only inflate / deflate cwnd.

        Why cwnd and not FlightSize (RFC 5681)? They are equal while the
        sender is window-limited, but right after Reno's inflated fast
        recovery FlightSize can be far larger than cwnd and would RAISE
        ssthresh on the next loss. Halving cwnd is what BSD Reno and ns-2 do.
        """
        if self.state == FAST_RECOVERY:
            # Timeout inside fast recovery: cwnd is inflated, use ssthresh
            window = self.ssthresh
        else:
            window = self.cwnd
        value = window / 2.0
        if value < MIN_SSTHRESH:
            value = MIN_SSTHRESH
        return value

    def can_start_fast_retransmit(self, snd_una):
        """
        Only start a new fast retransmit if the hole is above "recover".
        Otherwise the dup ACKs are leftovers from a previous loss event
        (for example duplicates created by a go-back-N resend).
        """
        return snd_una > self.recover

    def on_timeout(self, highest_sent):
        """
        Retransmission timeout - identical in Tahoe, Reno and New Reno:
        ssthresh = cwnd/2, cwnd = 1, back to slow start.
        The sender then resends everything from snd_una (go-back-N).
        """
        self.timeouts += 1
        self.ssthresh = self.half_window()
        self.cwnd = 1.0
        # Timeout -> SLOW_START (also leaves FAST_RECOVERY if we were in it)
        self.state = SLOW_START
        self.recover = highest_sent

    # ----- to be implemented by each algorithm ----------------------------
    def on_ack(self, ack_no, newly_acked):
        raise NotImplementedError

    def on_dupack(self, dupack_count, snd_una, highest_sent):
        raise NotImplementedError
