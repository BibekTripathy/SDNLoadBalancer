"""
Turn a simulator run (its summary + event log) into summary numbers and
small time series that the plots and the dashboard can use.

Definitions (also written in the README):
  throughput   - data bytes that reached the receiver, duplicates included, per second
  goodput      - NEW in-order data delivered to the application, per second
  retransmissions          - every segment sent a second (third, ...) time
    needed_retransmissions - retransmissions that filled a real hole
    spurious_retransmissions - retransmissions of data the receiver already had
  packet loss rate - segments dropped at the bottleneck / segments sent
  RTT          - from every ACK (send time of the segment echoed in the ACK)
  recovery time - from the first resend after a loss until everything that
                  was sent before it is ACKed (see recovery_episodes)
"""


def percentile(values, fraction):
    """Simple percentile: sort, then pick the value at that position."""
    if len(values) == 0:
        return None
    ordered = sorted(values)
    index = round(fraction * (len(ordered) - 1))
    return ordered[index]


def average(values):
    if len(values) == 0:
        return None
    return sum(values) / len(values)


def rtt_samples_ms(rows, flow_id=None):
    samples = []
    for row in rows:
        if row["rtt"] == "":
            continue
        if flow_id is not None and row["flow"] != flow_id:
            continue
        samples.append(row["rtt"] * 1000.0)
    return samples


def compute_run_metrics(summary, rows):
    """
    Add up all flows of one run into one row of the summary table.

    Total throughput / goodput = total bytes of all flows / run time,
    where run time goes from the first flow's start to the end of the run.
    (Adding up per-flow rates would be wrong when flows start at different
    times, because each flow's rate uses its own, shorter, active time.)
    """
    totals = {
        "segments_sent": 0,
        "segments_received": 0,
        "segments_delivered": 0,
        "retransmissions": 0,
        "needed_retransmissions": 0,
        "spurious_retransmissions": 0,
        "drops": 0,
        "timeouts": 0,
        "fast_retransmits": 0,
    }
    per_flow_goodput = []
    first_start = None
    last_end = 0.0
    for flow in summary["flows"]:
        for key in totals:
            totals[key] = totals[key] + flow[key]
        per_flow_goodput.append(flow["goodput_mbps"])
        flow_end = flow["start_time"] + flow["active_time"]
        if first_start is None or flow["start_time"] < first_start:
            first_start = flow["start_time"]
        if flow_end > last_end:
            last_end = flow_end

    run_time = last_end - first_start
    if run_time <= 0:
        run_time = 1e-9
    bits_per_segment = summary["mss_bytes"] * 8.0

    if totals["segments_sent"] > 0:
        loss_rate = totals["drops"] / totals["segments_sent"]
    else:
        loss_rate = 0.0

    rtts = rtt_samples_ms(rows)
    metrics = dict(totals)
    metrics["throughput_mbps"] = totals["segments_received"] * bits_per_segment / run_time / 1e6
    metrics["goodput_mbps"] = totals["segments_delivered"] * bits_per_segment / run_time / 1e6
    metrics["packet_loss_rate"] = loss_rate
    metrics["avg_rtt_ms"] = average(rtts)
    metrics["p95_rtt_ms"] = percentile(rtts, 0.95)
    metrics["num_flows"] = len(summary["flows"])
    metrics["per_flow_goodput_mbps"] = per_flow_goodput
    metrics["jain_fairness"] = jain_fairness(per_flow_goodput)
    metrics["duration_s"] = summary["end_time"]

    # Recovery time: every episode of every flow together
    episodes = []
    for flow_id in range(len(summary["flows"])):
        episodes.extend(recovery_episodes(sim_recovery_events(rows, flow_id)))
    recovery = recovery_summary(episodes)
    for key in recovery:
        metrics[key] = recovery[key]

    # Round floats so the JSON stays readable
    for key in metrics:
        if isinstance(metrics[key], float):
            metrics[key] = round(metrics[key], 4)
    return metrics


def jain_fairness(values):
    """Jain's index: 1.0 = perfectly fair share, 1/n = one flow takes everything."""
    if len(values) == 0:
        return None
    total = sum(values)
    squares = 0.0
    for value in values:
        squares = squares + value * value
    if squares == 0:
        return None
    return (total * total) / (len(values) * squares)


# ---------------------------------------------------------------------------
# Time series (for plots and for the dashboard JSON)
# ---------------------------------------------------------------------------
def cwnd_series(rows, flow_id=0, bin_s=0.01):
    """
    cwnd / ssthresh / state over time for one flow, keeping at most one
    point per `bin_s` seconds (the last one in the bin). The full log has
    a row per packet, which is far too much for a browser chart.
    """
    series = []
    last_bin = None
    for row in rows:
        if row["flow"] != flow_id:
            continue
        this_bin = int(row["time"] / bin_s)
        point = {
            "time": row["time"],
            "cwnd": row["cwnd"],
            "ssthresh": row["ssthresh"],
            "state": row["state"],
        }
        if this_bin == last_bin:
            series[-1] = point      # replace: keep the last value in this bin
        else:
            series.append(point)
            last_bin = this_bin
    return series


def loss_events(rows, flow_id=0):
    """Drops, fast retransmits and timeouts of one flow (markers on the plots)."""
    interesting = ["DROP_SCRIPTED", "DROP_RANDOM", "DROP_QUEUE",
                   "FAST_RETRANSMIT", "TIMEOUT"]
    events = []
    for row in rows:
        if row["flow"] == flow_id and row["event"] in interesting:
            events.append({"time": row["time"], "event": row["event"],
                           "seq": row["seq"], "cwnd": row["cwnd"]})
    return events


def rate_series(rows, mss_bytes, duration, bin_s):
    """
    Throughput and goodput per time bin, all flows added together.
      throughput bin = (segments sent - segments dropped) in the bin
                       = data that got through the bottleneck
      goodput bin    = how far the cumulative ACK moved forward in the bin
                       = new data delivered
    """
    num_bins = int(duration / bin_s) + 1
    passed = []
    acked = []
    for _ in range(num_bins):
        passed.append(0)
        acked.append(0)

    highest_ack = {}   # flow id -> highest ACK seen so far
    for row in rows:
        index = int(row["time"] / bin_s)
        if index >= num_bins:
            continue
        event = row["event"]
        if event == "SEND":
            passed[index] = passed[index] + 1
        elif event.startswith("DROP_"):
            passed[index] = passed[index] - 1
        elif row["ack"] >= 0:
            previous = highest_ack.get(row["flow"], 0)
            if row["ack"] > previous:
                acked[index] = acked[index] + (row["ack"] - previous)
                highest_ack[row["flow"]] = row["ack"]

    series = []
    for index in range(num_bins):
        bits_per_segment = mss_bytes * 8.0
        series.append({
            "time": round(index * bin_s, 4),
            "throughput_mbps": round(passed[index] * bits_per_segment / bin_s / 1e6, 4),
            "goodput_mbps": round(acked[index] * bits_per_segment / bin_s / 1e6, 4),
        })
    return series


def rtt_series(rows, flow_id=0, bin_s=0.05):
    """Average RTT (ms) per time bin for one flow."""
    sums = {}
    counts = {}
    for row in rows:
        if row["rtt"] == "" or row["flow"] != flow_id:
            continue
        index = int(row["time"] / bin_s)
        sums[index] = sums.get(index, 0.0) + row["rtt"] * 1000.0
        counts[index] = counts.get(index, 0) + 1
    series = []
    for index in sorted(sums):
        series.append({"time": round(index * bin_s, 4),
                       "rtt_ms": round(sums[index] / counts[index], 3)})
    return series


# ---------------------------------------------------------------------------
# Recovery time after a loss (simulator AND Mininet, same definition)
# ---------------------------------------------------------------------------
def recovery_episodes(events):
    """
    How long each loss recovery took.

    events: list of (time, kind, value) in time order, for ONE flow:
        ("send", end)   a NEW segment was sent; end = sequence just after it
        ("retx", 0)     a segment was RE-sent (fast retransmit or timeout)
        ("ack",  ack)   a cumulative ACK arrived

    An episode starts at the first resend and ends when the cumulative ACK
    covers everything that had been sent before that resend, i.e. every
    hole in that window is repaired. Resends during an episode belong to
    it. Units do not matter (segments in the simulator, bytes in a pcap).

    Returns a list of {"start", "end", "duration"} (an episode still open
    at the end of the run is left out: its length is unknown).
    """
    episodes = []
    highest_sent = 0
    in_episode = False
    start = 0.0
    target = 0
    for time_s, kind, value in events:
        if kind == "send":
            if value > highest_sent:
                highest_sent = value
        elif kind == "retx":
            if not in_episode:
                in_episode = True
                start = time_s
                target = highest_sent     # all of this must be ACKed to finish
        elif kind == "ack":
            if in_episode and value >= target:
                in_episode = False
                episodes.append({"start": start, "end": time_s,
                                 "duration": round(time_s - start, 6)})
    return episodes


def sim_recovery_events(rows, flow_id):
    """Simulator event log -> (time, kind, value) list for recovery_episodes."""
    events = []
    for row in rows:
        if row["flow"] != flow_id:
            continue
        if row["event"] == "SEND":
            if row["retransmit"]:
                events.append((row["time"], "retx", 0))
            else:
                events.append((row["time"], "send", row["seq"] + 1))
        elif row["ack"] >= 0 and not row["event"].startswith("DROP_"):
            events.append((row["time"], "ack", row["ack"]))
    return events


def pcap_recovery_events(seq_rows):
    """Rows of a Mininet flow<i>_seq.csv (strings) -> list for recovery_episodes."""
    events = []
    for row in seq_rows:
        time_s = float(row["time"])
        if row["direction"] == "DATA":
            if row["retransmission"] == "1":
                events.append((time_s, "retx", 0))
            else:
                events.append((time_s, "send", int(row["seq"]) + int(row["len"])))
        elif row["direction"] == "ACK" and row["ack"] != "":
            events.append((time_s, "ack", int(row["ack"])))
    return events


def recovery_summary(episodes):
    """Number of episodes, average and longest recovery time (seconds)."""
    durations = []
    for episode in episodes:
        durations.append(episode["duration"])
    if len(durations) == 0:
        return {"recovery_episodes": 0, "avg_recovery_s": None, "max_recovery_s": None}
    return {"recovery_episodes": len(durations),
            "avg_recovery_s": round(average(durations), 4),
            "max_recovery_s": round(max(durations), 4)}
