"""
Retransmission timeout (RTO) estimator - simple version of RFC 6298.

  first sample R:   SRTT = R,  RTTVAR = R / 2
  later samples R:  RTTVAR = 3/4 * RTTVAR + 1/4 * |SRTT - R|
                    SRTT   = 7/8 * SRTT   + 1/8 * R
  RTO = SRTT + 4 * RTTVAR, clamped to [min_rto, max_rto]

On every timeout the RTO is doubled (exponential backoff). The backoff
is cleared as soon as a new RTT sample arrives.

RFC 6298 recommends min_rto = 1 s; Linux uses 200 ms. We default to
200 ms so the simulator is comparable with the Mininet experiments.
"""


class RtoEstimator:
    def __init__(self, initial_rto=1.0, min_rto=0.2, max_rto=60.0):
        self.srtt = None
        self.rttvar = None
        self.min_rto = min_rto
        self.max_rto = max_rto
        self.base_rto = initial_rto
        self.backoff = 1

    def add_sample(self, rtt):
        if self.srtt is None:
            # First measurement
            self.srtt = rtt
            self.rttvar = rtt / 2.0
        else:
            # Update RTTVAR first (it uses the old SRTT), then SRTT
            self.rttvar = 0.75 * self.rttvar + 0.25 * abs(self.srtt - rtt)
            self.srtt = 0.875 * self.srtt + 0.125 * rtt

        self.base_rto = self.srtt + 4.0 * self.rttvar
        # A fresh sample means the path works again -> reset backoff
        self.backoff = 1

    def on_timeout(self):
        # Timeout -> exponential backoff (RTO doubles each time)
        self.backoff = self.backoff * 2

    def get_rto(self):
        rto = self.base_rto * self.backoff
        if rto < self.min_rto:
            rto = self.min_rto
        if rto > self.max_rto:
            rto = self.max_rto
        return rto
