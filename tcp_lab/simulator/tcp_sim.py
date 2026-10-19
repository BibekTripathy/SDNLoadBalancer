r"""
Event-driven, per-packet TCP simulator.

Network model (a "dumbbell"):

    sender 0 --(access delay)--\                                   /-- receiver 0
    sender 1 --(access delay)---[ drop-tail queue ]==bottleneck==>---- receiver 1
    UDP src  --(access delay)--/   (bandwidth, delay, loss)        \-- receiver 2
                       <------------- ACKs come back --------------

  - Data packets go through ONE shared bottleneck link: a FIFO drop-tail
    queue of `queue_size` packets, serialised at `bandwidth_mbps`, then
    `delay_ms` of propagation delay.
  - Packets can be dropped at the bottleneck for three reasons:
      DROP_SCRIPTED - we asked for (flow, seq) to be dropped (deterministic
                      experiments; each listed seq is dropped only once)
      DROP_RANDOM   - random loss with probability `loss_rate`
      DROP_QUEUE    - the queue was full (real congestion)
  - ACKs return over an uncongested reverse path (same propagation delay,
    no queue, no loss). This is a simplification: ACKs are tiny.
  - The receiver ACKs every segment immediately (no delayed ACKs) with a
    cumulative ACK = next expected segment number, and echoes the send
    time of the segment that triggered it (like the TCP timestamp option),
    so every ACK gives a valid RTT sample.
  - The ACK also says whether the segment that triggered it was a
    retransmission. A duplicate ACK caused by a retransmitted segment is
    NOT counted as a dup ACK: it only means an old copy arrived twice
    (e.g. Tahoe's go-back-N), not that new data is missing. This is the
    idea of the RFC 6582 "timestamp heuristic".

How the simulation runs: there is a list of future events sorted by time
(a heap). We repeatedly take the earliest event, set the clock to its
time, and call its handler function. Handlers schedule new events.

Every interesting thing that happens is appended to `sim.log_rows`
(a list of dicts) which the scenario runner writes to CSV.
"""

import heapq
import random
from collections import deque

from tcp_lab.simulator import make_algorithm
from tcp_lab.simulator.base import ACTION_GO_BACK_N, ACTION_RETRANSMIT, FAST_RECOVERY
from tcp_lab.simulator.rto import RtoEstimator

# Columns of the event log CSV, in order
LOG_COLUMNS = [
    "time", "flow", "algorithm", "event", "cwnd", "ssthresh", "state",
    "seq", "ack", "dupacks", "retransmit", "rtt", "queue_len",
]


class Packet:
    def __init__(self, kind, flow_id, seq=-1, ack=-1, size_bytes=1500,
                 send_time=0.0, echo_time=0.0, retransmit=False,
                 echo_retransmit=False):
        self.kind = kind            # "DATA", "ACK" or "UDP"
        self.flow_id = flow_id
        self.seq = seq              # segment number (DATA)
        self.ack = ack              # next expected segment (ACK)
        self.size_bytes = size_bytes
        self.send_time = send_time  # when the DATA segment left the sender
        self.echo_time = echo_time  # ACK: send_time of the segment that caused it
        self.retransmit = retransmit
        self.echo_retransmit = echo_retransmit  # ACK: was the triggering segment a resend?


# ---------------------------------------------------------------------------
# Bottleneck link
# ---------------------------------------------------------------------------
class BottleneckLink:
    def __init__(self, sim, bandwidth_mbps, delay_ms, queue_size, loss_rate):
        self.sim = sim
        self.bandwidth_bps = bandwidth_mbps * 1e6
        self.delay = delay_ms / 1000.0
        self.queue_size = queue_size
        self.loss_rate = loss_rate
        self.queue = deque()
        self.busy = False
        self.packets_in = 0
        self.packets_dropped = 0
        self.bytes_delivered = 0

    def receive(self, packet):
        """A packet arrives at the bottleneck router."""
        self.packets_in += 1

        # 1) Scripted drop (only for TCP data, only on the FIRST transmission)
        if packet.kind == "DATA":
            flow = self.sim.flows[packet.flow_id]
            if packet.seq in flow.scripted_drops and not packet.retransmit:
                flow.scripted_drops.remove(packet.seq)
                self.drop(packet, "DROP_SCRIPTED")
                return

        # 2) Random loss
        if self.loss_rate > 0 and self.sim.rng.random() < self.loss_rate:
            self.drop(packet, "DROP_RANDOM")
            return

        # 3) Drop-tail: queue already full -> drop the arriving packet
        if len(self.queue) >= self.queue_size:
            self.drop(packet, "DROP_QUEUE")
            return

        self.queue.append(packet)
        if not self.busy:
            self.start_next_transmission()

    def drop(self, packet, reason):
        self.packets_dropped += 1
        if packet.kind == "DATA":
            flow = self.sim.flows[packet.flow_id]
            flow.drops += 1
            flow.log(reason, seq=packet.seq, retransmit=packet.retransmit)
        else:
            self.sim.udp_dropped += 1

    def start_next_transmission(self):
        if len(self.queue) == 0:
            self.busy = False
            return
        self.busy = True
        packet = self.queue.popleft()
        transmission_time = packet.size_bytes * 8.0 / self.bandwidth_bps
        self.sim.schedule(transmission_time, self.transmission_done, packet)

    def transmission_done(self, packet):
        # Last bit is on the wire: it reaches the far side after the propagation delay
        self.bytes_delivered += packet.size_bytes
        self.sim.schedule(self.delay, self.sim.deliver_packet, packet)
        self.start_next_transmission()

    def set_bandwidth(self, bandwidth_mbps):
        self.bandwidth_bps = bandwidth_mbps * 1e6


# ---------------------------------------------------------------------------
# TCP flow = sender + receiver
# ---------------------------------------------------------------------------
class TcpFlow:
    def __init__(self, sim, flow_id, algorithm, start_time, total_segments,
                 access_delay_ms, initial_cwnd, initial_ssthresh, rwnd,
                 scripted_drops):
        self.sim = sim
        self.flow_id = flow_id
        self.algorithm_name = algorithm
        self.cc = make_algorithm(algorithm, initial_cwnd, initial_ssthresh)
        self.rto = RtoEstimator(initial_rto=sim.initial_rto, min_rto=sim.min_rto)
        self.start_time = start_time
        self.total_segments = total_segments   # None = send forever
        self.access_delay = access_delay_ms / 1000.0
        self.rwnd = rwnd
        self.scripted_drops = set(scripted_drops)

        # Sender variables (all in segment numbers)
        self.snd_una = 0          # oldest unacknowledged segment
        self.snd_nxt = 0          # next segment to send
        self.highest_sent = -1    # highest segment ever sent
        self.dupacks = 0
        self.timer_running = False
        self.timer_version = 0    # used to ignore cancelled timers
        self.done = False
        self.finish_time = None

        # Receiver variables
        self.rcv_next = 0          # next in-order segment expected
        self.out_of_order = set()  # segments received above a hole
        self.duplicate_segments = 0
        self.segments_received = 0           # every data segment that arrived, duplicates too

        # Counters for the summary
        self.segments_sent = 0
        self.retransmissions = 0             # all retransmissions sent
        self.needed_retransmissions = 0      # arrived and filled a real hole
        self.spurious_retransmissions = 0    # arrived but the receiver already had it
        self.drops = 0
        self.last_rtt = None

    # ----- logging ---------------------------------------------------------
    def log(self, event, seq=-1, ack=-1, retransmit=False, rtt=None):
        row = {
            "time": round(self.sim.now, 6),
            "flow": self.flow_id,
            "algorithm": self.algorithm_name,
            "event": event,
            "cwnd": round(self.cc.get_cwnd(), 4),
            "ssthresh": round(self.cc.get_ssthresh(), 4),
            "state": self.cc.get_state(),
            "seq": seq,
            "ack": ack,
            "dupacks": self.dupacks,
            "retransmit": 1 if retransmit else 0,
            "rtt": "" if rtt is None else round(rtt, 6),
            "queue_len": len(self.sim.link.queue),
        }
        self.sim.add_log_row(row)

    # ----- sending ---------------------------------------------------------
    def start(self, _unused=None):
        self.log("START")
        self.try_send()

    def try_send(self):
        """Send new segments while the window allows it."""
        while not self.done:
            if self.total_segments is not None and self.snd_nxt >= self.total_segments:
                break
            window = int(self.cc.get_cwnd())   # whole segments only
            if window > self.rwnd:
                window = self.rwnd
            flight = self.snd_nxt - self.snd_una
            if flight >= window:
                break
            self.send_segment(self.snd_nxt)
            self.snd_nxt = self.snd_nxt + 1

    def send_segment(self, seq):
        is_retransmit = seq <= self.highest_sent
        if is_retransmit:
            self.retransmissions += 1
        if seq > self.highest_sent:
            self.highest_sent = seq
        self.segments_sent += 1

        packet = Packet("DATA", self.flow_id, seq=seq, size_bytes=self.sim.packet_bytes,
                        send_time=self.sim.now, retransmit=is_retransmit)
        self.log("SEND", seq=seq, retransmit=is_retransmit)
        # Travel over the access link to the bottleneck router
        self.sim.schedule(self.access_delay, self.sim.link.receive, packet)

        if not self.timer_running:
            self.start_timer()

    # ----- retransmission timer ------------------------------------------
    def start_timer(self):
        self.timer_version += 1
        self.timer_running = True
        self.sim.schedule(self.rto.get_rto(), self.on_timer, self.timer_version)

    def stop_timer(self):
        self.timer_version += 1   # any already scheduled timer becomes stale
        self.timer_running = False

    def restart_timer(self):
        self.stop_timer()
        self.start_timer()

    def on_timer(self, version):
        if version != self.timer_version or self.done:
            return   # this timer was cancelled or restarted
        self.timer_running = False

        # Retransmission timeout -> cwnd = 1, ssthresh = cwnd/2,
        # slow start again, and resend from snd_una (go-back-N)
        self.cc.on_timeout(self.highest_sent)
        self.rto.on_timeout()    # exponential backoff
        self.dupacks = 0
        self.log("TIMEOUT", seq=self.snd_una)
        self.snd_nxt = self.snd_una
        self.try_send()          # this restarts the timer with the doubled RTO

    # ----- ACK processing --------------------------------------------------
    def on_ack_arrival(self, packet):
        ack = packet.ack
        rtt = self.sim.now - packet.echo_time
        self.last_rtt = rtt

        if ack > self.snd_una:
            self.handle_new_ack(ack, rtt)
        elif ack == self.snd_una and self.highest_sent >= self.snd_una:
            if packet.echo_retransmit:
                # Duplicate ACK caused by an old copy of a segment arriving
                # again (we resent data the receiver already had). Not a
                # sign of a new loss, so do not count it.
                self.log("DUPACK_IGNORED", ack=ack, rtt=rtt)
            else:
                self.handle_dupack(ack, rtt)
        # else: an old ACK below snd_una - ignore it

        if not self.done:
            self.try_send()

    def handle_new_ack(self, ack, rtt):
        newly_acked = ack - self.snd_una
        self.snd_una = ack
        self.dupacks = 0
        if self.snd_nxt < self.snd_una:
            # A cumulative ACK can jump past what go-back-N has resent so far
            self.snd_nxt = self.snd_una
        self.rto.add_sample(rtt)

        was_in_recovery = self.cc.get_state() == FAST_RECOVERY
        action = self.cc.on_ack(ack, newly_acked)
        still_in_recovery = self.cc.get_state() == FAST_RECOVERY

        if action == ACTION_RETRANSMIT:
            # New Reno partial ACK -> the next hole is snd_una, resend it now
            self.log("PARTIAL_ACK", ack=ack, rtt=rtt)
            self.send_segment(self.snd_una)
        elif was_in_recovery and not still_in_recovery:
            self.log("RECOVERY_EXIT", ack=ack, rtt=rtt)
        else:
            self.log("ACK", ack=ack, rtt=rtt)

        # Finished?
        if self.total_segments is not None and self.snd_una >= self.total_segments:
            self.done = True
            self.finish_time = self.sim.now
            self.stop_timer()
            self.log("FINISH", ack=ack)
            return

        # Restart the timer if data is still outstanding, otherwise stop it
        if self.snd_una <= self.highest_sent:
            self.restart_timer()
        else:
            self.stop_timer()

    def handle_dupack(self, ack, rtt):
        # Same cumulative ACK again -> duplicate ACK
        self.dupacks = self.dupacks + 1
        action = self.cc.on_dupack(self.dupacks, self.snd_una, self.highest_sent)

        if action == ACTION_RETRANSMIT:
            # Reno / New Reno: 3 dup ACKs -> fast retransmit the hole
            self.log("FAST_RETRANSMIT", seq=self.snd_una, ack=ack, rtt=rtt)
            self.send_segment(self.snd_una)
            self.restart_timer()
        elif action == ACTION_GO_BACK_N:
            # Tahoe: 3 dup ACKs -> fast retransmit, then slow start from snd_una
            self.log("FAST_RETRANSMIT", seq=self.snd_una, ack=ack, rtt=rtt)
            self.snd_nxt = self.snd_una
            self.stop_timer()   # try_send() starts it again with the resend
        else:
            self.log("DUPACK", ack=ack, rtt=rtt)

    # ----- receiver side ---------------------------------------------------
    def on_data_arrival(self, packet):
        seq = packet.seq
        self.segments_received += 1

        # Classify retransmissions when they reach the receiver:
        #   needed   -> it fills a hole (the original really was lost)
        #   spurious -> the receiver already had this segment (wasted bandwidth,
        #               e.g. Tahoe's go-back-N resending data that arrived fine)
        # A retransmission that is itself dropped never arrives, so it is
        # counted in neither group.
        if packet.retransmit:
            already_have_it = seq < self.rcv_next or seq in self.out_of_order
            if already_have_it:
                self.spurious_retransmissions += 1
                self.log("SPURIOUS_RETX", seq=seq, retransmit=True)
            else:
                self.needed_retransmissions += 1

        if seq == self.rcv_next:
            # In-order segment: advance, then pull in any buffered segments
            self.rcv_next = self.rcv_next + 1
            while self.rcv_next in self.out_of_order:
                self.out_of_order.remove(self.rcv_next)
                self.rcv_next = self.rcv_next + 1
        elif seq > self.rcv_next:
            # Segment above a hole: buffer it (the ACK will be a duplicate)
            self.out_of_order.add(seq)
        else:
            # We already have this segment (e.g. go-back-N resend)
            self.duplicate_segments += 1

        # Send a cumulative ACK straight back (reverse path: no queue, no loss)
        ack_packet = Packet("ACK", self.flow_id, ack=self.rcv_next, size_bytes=40,
                            echo_time=packet.send_time,
                            echo_retransmit=packet.retransmit)
        return_delay = self.sim.link.delay + self.access_delay
        self.sim.schedule(return_delay, self.on_ack_arrival, ack_packet)

    # ----- summary ---------------------------------------------------------
    def get_stats(self):
        end_time = self.finish_time
        if end_time is None:
            end_time = self.sim.now
        active_time = end_time - self.start_time
        if active_time <= 0:
            active_time = 1e-9
        # throughput = every data byte that reached the receiver (duplicates included)
        # goodput    = only NEW, in-order data handed to the application
        # So goodput <= throughput, and the gap is wasted (spurious) resends.
        throughput_bytes = self.segments_received * self.sim.mss_bytes
        goodput_bytes = self.rcv_next * self.sim.mss_bytes
        return {
            "flow": self.flow_id,
            "algorithm": self.algorithm_name,
            "start_time": self.start_time,
            "active_time": active_time,
            "segments_sent": self.segments_sent,
            "segments_received": self.segments_received,
            "segments_delivered": self.rcv_next,
            "retransmissions": self.retransmissions,
            "needed_retransmissions": self.needed_retransmissions,
            "spurious_retransmissions": self.spurious_retransmissions,
            "drops": self.drops,
            "timeouts": self.cc.timeouts,
            "fast_retransmits": self.cc.fast_retransmits,
            "duplicate_segments_at_receiver": self.duplicate_segments,
            "finished": self.done,
            "finish_time": self.finish_time,
            "throughput_mbps": throughput_bytes * 8.0 / active_time / 1e6,
            "goodput_mbps": goodput_bytes * 8.0 / active_time / 1e6,
        }


# ---------------------------------------------------------------------------
# UDP background source (constant bit rate, no congestion control)
# ---------------------------------------------------------------------------
class UdpSource:
    def __init__(self, sim, rate_mbps, start_time, stop_time, packet_bytes=1500):
        self.sim = sim
        self.rate_mbps = rate_mbps
        self.start_time = start_time
        self.stop_time = stop_time
        self.packet_bytes = packet_bytes
        self.packets_sent = 0

    def send_next(self, _unused=None):
        if self.sim.now >= self.stop_time or self.rate_mbps <= 0:
            return
        packet = Packet("UDP", -1, size_bytes=self.packet_bytes)
        self.sim.link.receive(packet)
        self.packets_sent += 1
        gap = self.packet_bytes * 8.0 / (self.rate_mbps * 1e6)
        self.sim.schedule(gap, self.send_next, None)


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, bandwidth_mbps=10.0, delay_ms=20.0, queue_size=50,
                 loss_rate=0.0, duration=10.0, seed=1, mss_bytes=1460,
                 header_bytes=40, initial_rto=1.0, min_rto=0.2):
        self.now = 0.0
        self.duration = duration
        self.events = []
        self.event_counter = 0     # tie-breaker so equal times keep insertion order
        self.rng = random.Random(seed)
        self.mss_bytes = mss_bytes
        self.packet_bytes = mss_bytes + header_bytes
        self.initial_rto = initial_rto
        self.min_rto = min_rto
        self.link = BottleneckLink(self, bandwidth_mbps, delay_ms, queue_size, loss_rate)
        self.flows = []
        self.udp_sources = []
        self.udp_dropped = 0
        self.log_rows = []
        self.network_events = []   # bandwidth / loss changes, for plots
        self.log_callback = None   # optional function(row), e.g. live streaming

    # ----- event queue -----------------------------------------------------
    def schedule(self, delay, handler, data):
        """Call handler(data) `delay` seconds from now."""
        self.event_counter += 1
        heapq.heappush(self.events, (self.now + delay, self.event_counter, handler, data))

    def add_log_row(self, row):
        self.log_rows.append(row)
        if self.log_callback is not None:
            self.log_callback(row)

    # ----- building the experiment ----------------------------------------
    def add_flow(self, algorithm, start_time=0.0, total_segments=None,
                 access_delay_ms=0.0, initial_cwnd=1, initial_ssthresh=64,
                 rwnd=1000, scripted_drops=None):
        if scripted_drops is None:
            scripted_drops = []
        flow_id = len(self.flows)
        flow = TcpFlow(self, flow_id, algorithm, start_time, total_segments,
                       access_delay_ms, initial_cwnd, initial_ssthresh, rwnd,
                       scripted_drops)
        self.flows.append(flow)
        self.event_counter += 1
        heapq.heappush(self.events, (start_time, self.event_counter, flow.start, None))
        return flow

    def add_udp_source(self, rate_mbps, start_time=0.0, stop_time=None):
        if stop_time is None:
            stop_time = self.duration
        source = UdpSource(self, rate_mbps, start_time, stop_time, self.packet_bytes)
        self.udp_sources.append(source)
        self.event_counter += 1
        heapq.heappush(self.events, (start_time, self.event_counter, source.send_next, None))
        return source

    def change_bandwidth_at(self, time, bandwidth_mbps):
        self.event_counter += 1
        heapq.heappush(self.events, (time, self.event_counter, self._apply_bandwidth, bandwidth_mbps))

    def change_loss_rate_at(self, time, loss_rate):
        self.event_counter += 1
        heapq.heappush(self.events, (time, self.event_counter, self._apply_loss_rate, loss_rate))

    def _apply_bandwidth(self, bandwidth_mbps):
        self.link.set_bandwidth(bandwidth_mbps)
        self.network_events.append({"time": self.now, "type": "BANDWIDTH", "value": bandwidth_mbps})

    def _apply_loss_rate(self, loss_rate):
        self.link.loss_rate = loss_rate
        self.network_events.append({"time": self.now, "type": "LOSS_RATE", "value": loss_rate})

    # ----- delivery at the far end of the bottleneck ----------------------
    def deliver_packet(self, packet):
        if packet.kind == "DATA":
            self.flows[packet.flow_id].on_data_arrival(packet)
        # UDP packets are simply absorbed by their receiver

    # ----- main loop -------------------------------------------------------
    def all_flows_done(self):
        if len(self.flows) == 0:
            return False
        for flow in self.flows:
            if not flow.done:
                return False
        return True

    def run(self):
        while len(self.events) > 0:
            event_time, _counter, handler, data = heapq.heappop(self.events)
            if event_time > self.duration:
                break
            self.now = event_time
            handler(data)
            if self.all_flows_done():
                break
        return self.get_summary()

    def get_summary(self):
        flow_stats = []
        for flow in self.flows:
            flow_stats.append(flow.get_stats())
        return {
            "end_time": self.now,
            "mss_bytes": self.mss_bytes,
            "flows": flow_stats,
            "link_packets_in": self.link.packets_in,
            "link_packets_dropped": self.link.packets_dropped,
            "udp_dropped": self.udp_dropped,
            "network_events": self.network_events,
        }
