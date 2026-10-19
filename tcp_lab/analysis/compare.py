"""
Simulator vs Mininet, and a simple formula to explain loss-limited results.

1) VALIDATION. Linux has no Tahoe, and Linux "reno" with SACK off recovers
   like New Reno. So for every variant that ran on both, we compare
   linux_reno (mininet) with Reno and New Reno (simulator) and say which
   one is closer. This checks the simulator; it is not a ranking (see
   scoring.py for that).

   The fair comparison uses simulator runs that START like Linux: with no
   ssthresh limit (run_sim_scenarios.py "linux_start_results"). Our normal
   scenarios start with ssthresh 32, which avoids the first-slow-start
   overshoot that Linux always has on a clean link.

   Expected differences, so a gap is not automatically a bug:
     - Linux receivers delay ACKs (one ACK per two segments), the
       simulator ACKs every segment -> Linux grows cwnd more slowly
       in congestion avoidance.
     - (handled by the Linux-like-start runs) Linux has no initial
       ssthresh, the normal simulator runs start with 32.
     - Linux reduces cwnd gradually during recovery (Proportional Rate
       Reduction, RFC 6937) instead of inflating it like Reno, and paces
       its window growth differently in detail.
     - MSS is 1448 bytes in Linux (timestamps option), 1460 in the simulator.

2) THE MATHIS FORMULA (Mathis, Semke, Mahdavi, Ott 1997). A Reno-style
   flow that loses a fraction p of its packets at random settles at

       rate = (MSS / RTT) * C / sqrt(p),      C = sqrt(3 / (2 b))

   where b is the number of segments each ACK covers (b = 1: ACK every
   segment, C = 1.22; b = 2: delayed ACKs, C = 0.87). The reason: after
   each loss the window halves and grows by 1 per RTT, so the AVERAGE
   window is about C / sqrt(p) segments, whatever the link can carry.
   It cannot be more than the link rate, so we cap it there.
   Numbers from it are labelled "model", never "simulator" or "mininet".
"""

import math

SIM_MSS_BYTES = 1460
LINUX_MSS_BYTES = 1448


def mathis_window_segments(loss_rate, acks_per_segment=1):
    """Average window (segments) a Reno-style flow can keep at loss rate p."""
    c = math.sqrt(3.0 / (2.0 * acks_per_segment))
    return c / math.sqrt(loss_rate)


def mathis_rate_mbps(mss_bytes, rtt_s, loss_rate, link_mbps, acks_per_segment=1):
    """Predicted goodput in Mbit/s, never more than the link rate."""
    if loss_rate <= 0:
        return link_mbps
    window = mathis_window_segments(loss_rate, acks_per_segment)
    rate = window * mss_bytes * 8.0 / rtt_s / 1e6
    if rate > link_mbps:
        return link_mbps
    return rate


def bdp_segments(link_mbps, rtt_s, mss_bytes):
    """Bandwidth-delay product: how many segments fill the path for one RTT."""
    return link_mbps * 1e6 * rtt_s / 8.0 / mss_bytes


def model_for_network(network):
    """
    The formula's view of one simulator network setting (base RTT only,
    queueing delay ignored). Returns None when there is no random loss.
    """
    loss = network["loss_rate"]
    if loss <= 0:
        return None
    rtt_s = 2.0 * network["delay_ms"] / 1000.0
    link = network["bandwidth_mbps"]
    return {
        "source": "model",
        "base_rtt_ms": round(rtt_s * 1000.0, 1),
        "loss_rate": loss,
        "bdp_segments": round(bdp_segments(link, rtt_s, SIM_MSS_BYTES), 1),
        "loss_window_segments": round(mathis_window_segments(loss, 1), 1),
        "loss_window_segments_delayed_ack": round(mathis_window_segments(loss, 2), 1),
        # simulator: MSS 1460, an ACK per segment
        "goodput_sim_style_mbps": round(mathis_rate_mbps(SIM_MSS_BYTES, rtt_s, loss, link, 1), 3),
        # Linux: MSS 1448, delayed ACKs
        "goodput_linux_style_mbps": round(mathis_rate_mbps(LINUX_MSS_BYTES, rtt_s, loss, link, 2), 3),
    }


def closest_algorithm(target_mean, sim_stats, metric):
    """The simulated algorithm whose mean `metric` is nearest to target_mean."""
    best = None
    best_gap = None
    for algorithm in sim_stats:
        mean = sim_stats[algorithm][metric]["mean"]
        if mean is None:
            continue
        gap = abs(mean - target_mean)
        if best_gap is None or gap < best_gap:
            best = algorithm
            best_gap = gap
    return best


def percent_difference(value, reference):
    """(value - reference) / reference in %, None if it cannot be computed."""
    if value is None or reference is None or reference == 0:
        return None
    return round((value - reference) / reference * 100.0, 1)


def mean_of(stats_by_algorithm, algorithm, metric):
    if algorithm not in stats_by_algorithm:
        return None
    return stats_by_algorithm[algorithm][metric]["mean"]


def validate_variant(sim_stats, linux_start_stats, mininet_stats):
    """
    One row of the validation table.

    sim_stats          {algorithm: {metric: describe}}  normal simulator runs (ssthresh 32)
    linux_start_stats  {algorithm: {metric: describe}}  reno / newreno with an unlimited
                                                        initial ssthresh, like Linux
    mininet_stats      {metric: describe}               linux_reno

    Linux is compared with the Linux-like-start runs, because only those
    start the same way. "Closer" is decided on goodput; for timeouts we
    only say whether Linux had more, fewer or in between.
    """
    row = {
        "mininet_goodput": mininet_stats["goodput_mbps"],
        "mininet_timeouts": mininet_stats["timeouts"]["mean"],
        "newreno_goodput": mean_of(sim_stats, "newreno", "goodput_mbps"),
        "newreno_linux_start_goodput": mean_of(linux_start_stats, "newreno", "goodput_mbps"),
        "reno_linux_start_goodput": mean_of(linux_start_stats, "reno", "goodput_mbps"),
        "newreno_linux_start_timeouts": mean_of(linux_start_stats, "newreno", "timeouts"),
        "reno_linux_start_timeouts": mean_of(linux_start_stats, "reno", "timeouts"),
        "goodput_vs_newreno_linux_start_pct": None,
        "closer_by_goodput": None,
        # "more than both", "fewer than both" or "between" the two simulated algorithms
        "timeouts_vs_simulator": None,
        "mininet_spurious": mininet_stats["spurious_retransmissions"]["mean"],
    }
    linux_goodput = mininet_stats["goodput_mbps"]["mean"]
    if linux_goodput is None or len(linux_start_stats) == 0:
        return row
    row["goodput_vs_newreno_linux_start_pct"] = percent_difference(
        linux_goodput, row["newreno_linux_start_goodput"])
    row["closer_by_goodput"] = closest_algorithm(linux_goodput, linux_start_stats, "goodput_mbps")
    row["timeouts_vs_simulator"] = compare_to_pair(row["mininet_timeouts"],
                                                   row["newreno_linux_start_timeouts"],
                                                   row["reno_linux_start_timeouts"])
    return row


def compare_to_pair(value, first, second):
    """Where `value` lies relative to two others. (Not "closest": when Linux has
    more timeouts than both, the closest one is just the bigger of the two.)"""
    if value is None or first is None or second is None:
        return None
    if value > max(first, second):
        return "more than both"
    if value < min(first, second):
        return "fewer than both"
    return "between"
