"""
Unit tests for the TCP Congestion Control Lab simulator.

Part 1 drives the algorithm classes directly with hand-computed numbers.
Part 2 runs the network simulator on a small, hand-checkable single-loss
case and on multiple-loss cases.
"""

import pytest

from tcp_lab.simulator import make_algorithm
from tcp_lab.simulator.base import (
    ACTION_GO_BACK_N,
    ACTION_NONE,
    ACTION_RETRANSMIT,
    CONG_AVOID,
    FAST_RECOVERY,
    SLOW_START,
)
from tcp_lab.simulator.rto import RtoEstimator
from tcp_lab.simulator.tcp_sim import Simulator


# ---------------------------------------------------------------------------
# Part 1: algorithm state machines (no network)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["tahoe", "reno", "newreno"])
def test_slow_start_then_congestion_avoidance(name):
    cc = make_algorithm(name, initial_cwnd=1, initial_ssthresh=4)
    assert cc.get_state() == SLOW_START
    # Slow start: +1 per ACK -> 2, 3, 4
    for expected in [2.0, 3.0, 4.0]:
        cc.on_ack(0, 1)
        assert cc.get_cwnd() == expected
    # cwnd reached ssthresh -> congestion avoidance
    assert cc.get_state() == CONG_AVOID
    # Congestion avoidance: +1/cwnd per ACK -> 4 + 1/4
    cc.on_ack(0, 1)
    assert cc.get_cwnd() == pytest.approx(4.25)


def test_tahoe_three_dupacks():
    cc = make_algorithm("tahoe")
    cc.cwnd = 10.0
    cc.state = CONG_AVOID
    # 1st and 2nd dup ACK: wait
    assert cc.on_dupack(1, 20, 29) == ACTION_NONE
    assert cc.on_dupack(2, 20, 29) == ACTION_NONE
    assert cc.get_cwnd() == 10.0
    # 3rd dup ACK: ssthresh = 10/2 = 5, cwnd = 1, slow start, go-back-N
    assert cc.on_dupack(3, 20, 29) == ACTION_GO_BACK_N
    assert cc.get_ssthresh() == 5.0
    assert cc.get_cwnd() == 1.0
    assert cc.get_state() == SLOW_START
    # Tahoe has no fast recovery: more dup ACKs change nothing
    assert cc.on_dupack(4, 20, 29) == ACTION_NONE
    assert cc.get_cwnd() == 1.0


def test_reno_fast_recovery_inflate_deflate():
    cc = make_algorithm("reno")
    cc.cwnd = 10.0
    cc.state = CONG_AVOID
    cc.on_dupack(1, 20, 29)
    cc.on_dupack(2, 20, 29)
    # 3rd dup ACK: ssthresh = 5, cwnd = 5 + 3 = 8
    assert cc.on_dupack(3, 20, 29) == ACTION_RETRANSMIT
    assert cc.get_ssthresh() == 5.0
    assert cc.get_cwnd() == 8.0
    assert cc.get_state() == FAST_RECOVERY
    # Inflate: +1 per extra dup ACK
    cc.on_dupack(4, 20, 29)
    cc.on_dupack(5, 20, 29)
    assert cc.get_cwnd() == 10.0
    # Any new ACK (even partial, ack 22 < recover) deflates and exits
    assert cc.on_ack(22, 2) == ACTION_NONE
    assert cc.get_cwnd() == 5.0
    assert cc.get_state() == CONG_AVOID


def test_newreno_partial_and_full_ack():
    cc = make_algorithm("newreno")
    cc.cwnd = 10.0
    cc.state = CONG_AVOID
    cc.on_dupack(1, 20, 29)
    cc.on_dupack(2, 20, 29)
    assert cc.on_dupack(3, 20, 29) == ACTION_RETRANSMIT
    assert cc.recover == 29
    assert cc.get_cwnd() == 8.0
    cc.on_dupack(4, 20, 29)
    cc.on_dupack(5, 20, 29)
    assert cc.get_cwnd() == 10.0
    # Partial ACK (22 <= recover): retransmit next hole, cwnd = 10 - 2 + 1 = 9
    assert cc.on_ack(22, 2) == ACTION_RETRANSMIT
    assert cc.get_cwnd() == 9.0
    assert cc.get_state() == FAST_RECOVERY
    # Full ACK (30 > recover): cwnd = ssthresh, leave fast recovery
    assert cc.on_ack(30, 8) == ACTION_NONE
    assert cc.get_cwnd() == 5.0
    assert cc.get_state() == CONG_AVOID


@pytest.mark.parametrize("name", ["tahoe", "reno", "newreno"])
def test_timeout_resets_to_slow_start(name):
    cc = make_algorithm(name)
    cc.cwnd = 8.0
    cc.state = CONG_AVOID
    # Timeout: ssthresh = 8/2 = 4, cwnd = 1, slow start
    cc.on_timeout(highest_sent=40)
    assert cc.get_ssthresh() == 4.0
    assert cc.get_cwnd() == 1.0
    assert cc.get_state() == SLOW_START
    assert cc.timeouts == 1
    # ssthresh never below 2 segments (cwnd is now 1 -> 1/2 -> clamped to 2)
    cc.on_timeout(highest_sent=40)
    assert cc.get_ssthresh() == 2.0


def test_timeout_during_fast_recovery_uses_real_window():
    # In fast recovery cwnd is inflated (12) but the real window is ssthresh (6).
    cc = make_algorithm("newreno")
    cc.cwnd = 12.0
    cc.ssthresh = 6.0
    cc.state = FAST_RECOVERY
    cc.on_timeout(highest_sent=40)
    assert cc.get_ssthresh() == 3.0
    assert cc.get_cwnd() == 1.0
    assert cc.get_state() == SLOW_START


def test_rto_estimator_rfc6298():
    rto = RtoEstimator(initial_rto=1.0, min_rto=0.2)
    assert rto.get_rto() == 1.0
    # First sample 100 ms: SRTT=0.1, RTTVAR=0.05, RTO = 0.1 + 4*0.05 = 0.3
    rto.add_sample(0.1)
    assert rto.get_rto() == pytest.approx(0.3)
    # Second sample 200 ms: RTTVAR = 0.75*0.05 + 0.25*0.1 = 0.0625
    #                      SRTT   = 0.875*0.1 + 0.125*0.2 = 0.1125
    rto.add_sample(0.2)
    assert rto.srtt == pytest.approx(0.1125)
    assert rto.rttvar == pytest.approx(0.0625)
    assert rto.get_rto() == pytest.approx(0.3625)
    # Exponential backoff
    rto.on_timeout()
    assert rto.get_rto() == pytest.approx(0.725)
    rto.on_timeout()
    assert rto.get_rto() == pytest.approx(1.45)
    # New sample clears the backoff; min RTO is respected
    rto.add_sample(0.001)
    assert rto.get_rto() >= 0.2


# ---------------------------------------------------------------------------
# Part 2: full simulation
# ---------------------------------------------------------------------------
def run_single_flow(algorithm, drops, total_segments=60):
    """
    Hand-checkable setup: a very fast link (1 Gbps, no queueing),
    10 ms one-way delay (RTT about 20 ms), initial ssthresh = 64 so the
    loss happens during slow start where cwnd is a whole number.
    """
    sim = Simulator(bandwidth_mbps=1000, delay_ms=10, queue_size=1000, duration=30)
    sim.add_flow(algorithm, total_segments=total_segments,
                 initial_ssthresh=64, scripted_drops=drops)
    summary = sim.run()
    return sim, summary["flows"][0]


def rows_with_event(sim, event):
    result = []
    for row in sim.log_rows:
        if row["event"] == event:
            result.append(row)
    return result


# Hand calculation for dropping segment 19:
#   segments 0..18 are ACKed -> 19 new ACKs in slow start -> cwnd = 1 + 19 = 20
#   (dup ACKs do not grow cwnd), so at the 3rd dup ACK: ssthresh = 20 / 2 = 10.
#   cwnd 20 means segments 19..38 were sent: 19 is lost, 20..38 give 19 dup ACKs.


def test_single_loss_tahoe_trace():
    sim, stats = run_single_flow("tahoe", [19])
    fast = rows_with_event(sim, "FAST_RETRANSMIT")
    assert len(fast) == 1
    assert fast[0]["seq"] == 19
    # Tahoe: cwnd = 1, back to slow start
    assert fast[0]["cwnd"] == 1.0
    assert fast[0]["ssthresh"] == 10.0
    assert fast[0]["state"] == SLOW_START
    assert stats["timeouts"] == 0
    assert stats["retransmissions"] == 1
    assert stats["spurious_retransmissions"] == 0
    assert stats["segments_delivered"] == 60


@pytest.mark.parametrize("name", ["reno", "newreno"])
def test_single_loss_reno_and_newreno_trace(name):
    # cwnd = ssthresh + 3 = 13, then +1 for each of the remaining
    # 19 - 3 = 16 dup ACKs (14 ... 29), then deflate to 10 on the new ACK.
    sim, stats = run_single_flow(name, [19])
    fast = rows_with_event(sim, "FAST_RETRANSMIT")
    assert len(fast) == 1
    assert fast[0]["cwnd"] == 13.0
    assert fast[0]["ssthresh"] == 10.0
    assert fast[0]["state"] == FAST_RECOVERY

    inflated = []
    for row in rows_with_event(sim, "DUPACK"):
        if row["state"] == FAST_RECOVERY:
            inflated.append(row["cwnd"])
    expected = []
    for value in range(14, 30):
        expected.append(float(value))
    assert inflated == expected

    exits = rows_with_event(sim, "RECOVERY_EXIT")
    assert len(exits) == 1
    assert exits[0]["cwnd"] == 10.0
    assert exits[0]["ack"] == 39       # everything up to 38 was buffered at the receiver
    assert exits[0]["state"] == CONG_AVOID
    assert stats["timeouts"] == 0
    assert stats["retransmissions"] == 1
    assert stats["needed_retransmissions"] == 1
    assert stats["segments_delivered"] == 60


@pytest.mark.parametrize("drops", [[20, 22], [20, 22, 24], [20, 22, 24, 26]])
def test_multiple_losses_in_one_window(drops):
    _, tahoe = run_single_flow("tahoe", drops)
    _, reno = run_single_flow("reno", drops)
    sim_nr, newreno = run_single_flow("newreno", drops)

    # Everyone eventually delivers all data
    for stats in [tahoe, reno, newreno]:
        assert stats["segments_delivered"] == 60

    # New Reno: one partial ACK per extra hole, no timeout
    assert newreno["timeouts"] == 0
    assert len(rows_with_event(sim_nr, "PARTIAL_ACK")) == len(drops) - 1

    assert newreno["fast_retransmits"] == 1

    # Reno leaves fast recovery on the first partial ACK, so every further
    # hole is a NEW loss event: either another fast retransmit (cwnd halved
    # again) or, when too few dup ACKs are left, a timeout.
    assert reno["fast_retransmits"] + reno["timeouts"] >= 2
    if len(drops) >= 3:
        assert reno["timeouts"] >= 1

    # Tahoe (go-back-N slow start) avoids the timeout but resends data the
    # receiver already had -> spurious retransmissions
    assert tahoe["timeouts"] == 0
    assert tahoe["fast_retransmits"] == 1
    assert tahoe["needed_retransmissions"] == len(drops)
    assert tahoe["spurious_retransmissions"] > 0

    # New Reno needs exactly one retransmission per lost segment, and finishes first
    assert newreno["retransmissions"] == len(drops)
    assert newreno["spurious_retransmissions"] == 0
    assert newreno["finish_time"] < reno["finish_time"]
    assert newreno["finish_time"] < tahoe["finish_time"]


def test_random_loss_is_reproducible():
    results = []
    for _ in range(2):
        sim = Simulator(bandwidth_mbps=10, delay_ms=20, queue_size=50, loss_rate=0.01,
                        duration=5, seed=42)
        sim.add_flow("newreno")
        summary = sim.run()
        results.append(summary["flows"][0]["segments_delivered"])
    assert results[0] == results[1]
    assert results[0] > 0


def test_drop_tail_queue_and_multiple_flows():
    # Two flows share a small queue -> real congestion drops, both progress
    sim = Simulator(bandwidth_mbps=5, delay_ms=20, queue_size=10, duration=10)
    sim.add_flow("reno")
    sim.add_flow("newreno", start_time=1.0)
    summary = sim.run()
    assert len(rows_with_event(sim, "DROP_QUEUE")) > 0
    for stats in summary["flows"]:
        assert stats["segments_delivered"] > 100
    # Total goodput can not exceed the link rate
    total = summary["flows"][0]["goodput_mbps"] + summary["flows"][1]["goodput_mbps"]
    assert total <= 5.0 * 1.05


def test_bandwidth_change_and_udp_background():
    sim = Simulator(bandwidth_mbps=10, delay_ms=10, queue_size=20, duration=6)
    sim.add_flow("newreno")
    sim.add_udp_source(rate_mbps=6, start_time=2.0, stop_time=4.0)
    sim.change_bandwidth_at(3.0, 2.0)
    summary = sim.run()
    assert summary["network_events"][0]["type"] == "BANDWIDTH"
    assert summary["network_events"][0]["value"] == 2.0
    assert sim.udp_sources[0].packets_sent > 0
    assert summary["link_packets_dropped"] > 0


def test_log_rows_have_all_columns():
    from tcp_lab.simulator.tcp_sim import LOG_COLUMNS
    sim, _ = run_single_flow("reno", [20], total_segments=30)
    for row in sim.log_rows:
        assert list(row.keys()) == LOG_COLUMNS
