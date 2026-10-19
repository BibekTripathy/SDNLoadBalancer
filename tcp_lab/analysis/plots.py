"""
Matplotlib plots for TCP Lab results (saved as PNG).

We use the "Agg" backend: it draws straight into image files and needs no
screen, so plotting works inside Mininet hosts, Docker and SSH sessions.

Every plotting function receives `runs`, a dict in the fixed order
tahoe -> reno -> newreno:
    runs[algorithm] = {"rows": event log rows, "summary": simulator summary}
Each algorithm always gets the same color in every figure.
"""

import matplotlib

matplotlib.use("Agg")   # must be set before pyplot is imported
import matplotlib.pyplot as plt

from tcp_lab.analysis import metrics

# One color per algorithm (identity), same in every plot
ALGORITHM_COLORS = {
    "tahoe": "#2a78d6",     # blue
    "reno": "#eb6834",      # orange
    "newreno": "#1baf7a",   # aqua
    "linux_reno": "#6250d6",  # violet - Mininet / real Linux results
}
ALGORITHM_LABELS = {
    "tahoe": "Tahoe",
    "reno": "Reno",
    "newreno": "New Reno",
    "linux_reno": "Linux reno (SACK off)",
}

# Background shading for the sender state (CONG_AVOID is left unshaded)
STATE_SHADES = {
    "SLOW_START": ("#eda100", 0.18, "Slow start"),
    "FAST_RECOVERY": ("#e87ba4", 0.30, "Fast recovery"),
}

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"


def style_axis(ax):
    """Quiet axes: light grid, no top/right border, grey labels."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(TEXT_SECONDARY)
    ax.spines["bottom"].set_color(TEXT_SECONDARY)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
    ax.xaxis.label.set_color(TEXT_SECONDARY)
    ax.yaxis.label.set_color(TEXT_SECONDARY)


def new_figure(num_rows, title, height_per_row=2.4):
    fig, axes = plt.subplots(num_rows, 1, figsize=(11, height_per_row * num_rows + 0.8),
                             sharex=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle(title, color=TEXT, fontsize=12, x=0.01, ha="left")
    result = []
    for row in axes:
        style_axis(row[0])
        result.append(row[0])
    return fig, result


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def mark_network_changes(ax, network_events):
    """Vertical dotted line + small label wherever bandwidth / loss changed."""
    for change in network_events:
        ax.axvline(change["time"], color=TEXT_SECONDARY, linestyle=":", linewidth=1)
        if change["type"] == "BANDWIDTH":
            text = str(change["value"]) + " Mbps"
        else:
            text = "loss " + str(change["value"])
        ax.text(change["time"], 1.0, " " + text, transform=ax.get_xaxis_transform(),
                fontsize=7, color=TEXT_SECONDARY, va="top")


# ---------------------------------------------------------------------------
# cwnd vs time
# ---------------------------------------------------------------------------
def shade_states(ax, series):
    """Shade the background wherever the sender was in slow start / fast recovery."""
    times = []
    for point in series:
        times.append(point["time"])
    for state in STATE_SHADES:
        color, alpha, label = STATE_SHADES[state]
        inside = []
        for point in series:
            inside.append(point["state"] == state)
        ax.fill_between(times, 0, 1, where=inside, step="post", color=color,
                        alpha=alpha, linewidth=0, label=label,
                        transform=ax.get_xaxis_transform())


def plot_cwnd(runs, title, path):
    """
    Top panel: cwnd of all algorithms overlaid.
    One panel per algorithm below it: cwnd + ssthresh, state shading,
    drops (x), fast retransmits (triangle) and timeouts (dashed line).
    Only flow 0 is drawn when there are several flows.
    """
    algorithms = list(runs.keys())
    fig, axes = new_figure(len(algorithms) + 1, title)

    overlay = axes[0]
    for algorithm in algorithms:
        series = metrics.cwnd_series(runs[algorithm]["rows"], flow_id=0)
        times = [p["time"] for p in series]
        cwnds = [p["cwnd"] for p in series]
        overlay.plot(times, cwnds, drawstyle="steps-post", linewidth=1.5,
                     color=ALGORITHM_COLORS[algorithm], label=ALGORITHM_LABELS[algorithm])
    overlay.set_ylabel("cwnd (segments)")
    overlay.set_title("All algorithms (flow 0)", fontsize=9, color=TEXT_SECONDARY, loc="left")
    overlay.legend(fontsize=8, frameon=False, loc="upper left")
    overlay.set_ylim(bottom=0)
    mark_network_changes(overlay, runs[algorithms[0]]["summary"]["network_events"])

    # Same y scale on every per-algorithm panel so they can be compared by eye
    highest = 1.0
    for algorithm in algorithms:
        for point in metrics.cwnd_series(runs[algorithm]["rows"], flow_id=0):
            if point["cwnd"] > highest:
                highest = point["cwnd"]

    for index in range(len(algorithms)):
        algorithm = algorithms[index]
        ax = axes[index + 1]
        rows = runs[algorithm]["rows"]
        series = metrics.cwnd_series(rows, flow_id=0)
        times = [p["time"] for p in series]
        cwnds = [p["cwnd"] for p in series]
        ssthreshs = [p["ssthresh"] for p in series]

        shade_states(ax, series)
        ax.plot(times, cwnds, drawstyle="steps-post", linewidth=1.5,
                color=ALGORITHM_COLORS[algorithm], label="cwnd")
        ax.plot(times, ssthreshs, drawstyle="steps-post", linewidth=1,
                color=TEXT_SECONDARY, linestyle="--", label="ssthresh")

        # Loss markers
        drop_t, drop_y, fr_t, fr_y, timeout_t = [], [], [], [], []
        for event in metrics.loss_events(rows, flow_id=0):
            if event["event"].startswith("DROP_"):
                drop_t.append(event["time"])
                drop_y.append(event["cwnd"])
            elif event["event"] == "FAST_RETRANSMIT":
                fr_t.append(event["time"])
                fr_y.append(event["cwnd"])
            else:
                timeout_t.append(event["time"])
        ax.scatter(drop_t, drop_y, marker="x", s=36, color=TEXT, label="packet dropped", zorder=3)
        ax.scatter(fr_t, fr_y, marker="v", s=40, color=TEXT_SECONDARY,
                   label="fast retransmit", zorder=3)
        for t in timeout_t:
            ax.axvline(t, color=TEXT, linestyle="--", linewidth=1)
        if len(timeout_t) > 0:
            ax.plot([], [], color=TEXT, linestyle="--", linewidth=1, label="timeout")

        stats = metrics.compute_run_metrics(runs[algorithm]["summary"], rows)
        subtitle = (ALGORITHM_LABELS[algorithm] + "   timeouts " + str(stats["timeouts"])
                    + ", fast retransmits " + str(stats["fast_retransmits"])
                    + ", goodput " + str(round(stats["goodput_mbps"], 2)) + " Mbps")
        ax.set_title(subtitle, fontsize=9, color=TEXT_SECONDARY, loc="left")
        ax.set_ylabel("cwnd (segments)")
        ax.set_ylim(0, highest * 1.1)
        ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=4)
        mark_network_changes(ax, runs[algorithm]["summary"]["network_events"])

    axes[-1].set_xlabel("time (s)")
    save(fig, path)


# ---------------------------------------------------------------------------
# Sequence number vs time
# ---------------------------------------------------------------------------
def plot_sequence(runs, title, path, time_window=None):
    """
    One panel per algorithm, flow 0:
      small dots = first transmission of a segment
      black circles = retransmissions
      violet x = spurious retransmissions (arrived but receiver already had them)
      grey line = cumulative ACK
    time_window = (start, end) only draws that part of the run (zoom).
    """
    algorithms = list(runs.keys())
    fig, axes = new_figure(len(algorithms), title)
    for index in range(len(algorithms)):
        algorithm = algorithms[index]
        ax = axes[index]
        new_t, new_s, retx_t, retx_s, spur_t, spur_s, ack_t, ack_s = [], [], [], [], [], [], [], []
        for row in runs[algorithm]["rows"]:
            if row["flow"] != 0:
                continue
            if time_window is not None:
                if row["time"] < time_window[0] or row["time"] > time_window[1]:
                    continue
            if row["event"] == "SEND":
                if row["retransmit"] == 1:
                    retx_t.append(row["time"])
                    retx_s.append(row["seq"])
                else:
                    new_t.append(row["time"])
                    new_s.append(row["seq"])
            elif row["event"] == "SPURIOUS_RETX":
                spur_t.append(row["time"])
                spur_s.append(row["seq"])
            elif row["ack"] >= 0:
                ack_t.append(row["time"])
                ack_s.append(row["ack"])

        ax.plot(ack_t, ack_s, drawstyle="steps-post", color=GRID, linewidth=2, label="cumulative ACK")
        ax.scatter(new_t, new_s, s=2, color=ALGORITHM_COLORS[algorithm], label="sent")
        ax.scatter(retx_t, retx_s, s=30, facecolors="none", edgecolors=TEXT,
                   label="retransmission (" + str(len(retx_t)) + ")", zorder=3)
        ax.scatter(spur_t, spur_s, s=30, marker="x", color="#6250d6",
                   label="spurious at receiver (" + str(len(spur_t)) + ")", zorder=4)
        ax.set_title(ALGORITHM_LABELS[algorithm], fontsize=9, color=TEXT_SECONDARY, loc="left")
        ax.set_ylabel("segment number")
        ax.legend(fontsize=7, frameon=False, loc="upper left", markerscale=1.5)
    axes[-1].set_xlabel("time (s)")
    save(fig, path)


def loss_zoom_window(runs, duration):
    """
    Time window around the losses: from just before the first drop until a
    little after the last retransmission (of any algorithm). None if no loss.
    """
    first_drop = None
    last_retransmit = None
    for algorithm in runs:
        for row in runs[algorithm]["rows"]:
            if row["flow"] != 0:
                continue
            if row["event"].startswith("DROP_") and first_drop is None:
                first_drop = row["time"]
            if row["event"] == "SEND" and row["retransmit"] == 1:
                if last_retransmit is None or row["time"] > last_retransmit:
                    last_retransmit = row["time"]
    if first_drop is None or last_retransmit is None:
        return None
    end = last_retransmit + 0.2
    if end > duration:
        end = duration
    return (first_drop - 0.05, end)


# ---------------------------------------------------------------------------
# RTT vs time
# ---------------------------------------------------------------------------
def plot_rtt(runs, title, path):
    algorithms = list(runs.keys())
    fig, axes = new_figure(1, title, height_per_row=3.2)
    ax = axes[0]
    for algorithm in algorithms:
        series = metrics.rtt_series(runs[algorithm]["rows"], flow_id=0)
        ax.plot([p["time"] for p in series], [p["rtt_ms"] for p in series],
                linewidth=1.5, color=ALGORITHM_COLORS[algorithm],
                label=ALGORITHM_LABELS[algorithm])
    ax.set_ylabel("RTT (ms, 50 ms average)")
    ax.set_xlabel("time (s)")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    mark_network_changes(ax, runs[algorithms[0]]["summary"]["network_events"])
    save(fig, path)


# ---------------------------------------------------------------------------
# Throughput and goodput vs time
# ---------------------------------------------------------------------------
def pick_bin_size(duration):
    """About 80 points per run, never finer than 100 ms."""
    size = duration / 80.0
    if size < 0.1:
        size = 0.1
    return size


def plot_throughput(runs, title, path, mss_bytes, duration):
    """Two panels sharing the time axis: throughput (top) and goodput (bottom)."""
    algorithms = list(runs.keys())
    fig, axes = new_figure(2, title, height_per_row=2.8)
    bin_s = pick_bin_size(duration)
    for algorithm in algorithms:
        series = metrics.rate_series(runs[algorithm]["rows"], mss_bytes, duration, bin_s)
        times = [p["time"] for p in series]
        axes[0].plot(times, [p["throughput_mbps"] for p in series], linewidth=1.5,
                     color=ALGORITHM_COLORS[algorithm], label=ALGORITHM_LABELS[algorithm])
        axes[1].plot(times, [p["goodput_mbps"] for p in series], linewidth=1.5,
                     color=ALGORITHM_COLORS[algorithm], label=ALGORITHM_LABELS[algorithm])
    axes[0].set_ylabel("throughput (Mbps)")
    axes[0].set_title("Throughput: all data through the bottleneck, resends included",
                      fontsize=9, color=TEXT_SECONDARY, loc="left")
    axes[1].set_ylabel("goodput (Mbps)")
    axes[1].set_title("Goodput: new data delivered to the application "
                      "(a spike = buffered data released at once when a hole is filled)",
                      fontsize=9, color=TEXT_SECONDARY, loc="left")
    axes[1].set_xlabel("time (s), " + str(round(bin_s, 2)) + " s bins, all flows added")
    for ax in axes:
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8, frameon=False, loc="lower right")
        mark_network_changes(ax, runs[algorithms[0]]["summary"]["network_events"])
    save(fig, path)


# ---------------------------------------------------------------------------
# Phase 5: repeated runs, simulator vs Mininet
# ---------------------------------------------------------------------------
# Order of the bars in every comparison chart; linux_reno is hatched so the
# real-Linux bar can never be mistaken for a simulated one
COMPARISON_ORDER = [("tahoe", "simulator"), ("reno", "simulator"),
                    ("newreno", "simulator"), ("linux_reno", "mininet")]

METRIC_TITLES = {
    "goodput_mbps": "Goodput (Mbit/s)",
    "retransmissions": "Retransmissions",
    "timeouts": "Timeouts",
    "avg_recovery_s": "Avg recovery time (s)",
}


def bar_values(variant_stats, algorithm, source, metric):
    """(mean, error below, error above) for one bar; None if there is no data."""
    if algorithm not in variant_stats[source]:
        return None
    stats = variant_stats[source][algorithm][metric]
    if stats["n"] == 0:
        return None
    return (stats["mean"], stats["mean"] - stats["min"], stats["max"] - stats["mean"])


def plot_scenario_comparison(scenario_id, scenario_name, variants, metrics_to_plot, path):
    """
    One panel per metric, one group of bars per variant. Bar = mean,
    whisker = min..max over seeds (simulator) or runs (mininet).
    variants: list of (label, variant_stats) where
        variant_stats = {"simulator": {algo: {metric: describe}}, "mininet": {...}}
    """
    fig, axes = plt.subplots(1, len(metrics_to_plot),
                             figsize=(4.2 * len(metrics_to_plot) + 1, 3.8), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle(scenario_id + " " + scenario_name
                 + "  -  bars: mean, whiskers: min..max over seeds (simulator) / runs (mininet)."
                 + "  Simulator flows start with ssthresh 32, Linux with no limit"
                 + " (see the validation table)",
                 color=TEXT, fontsize=10, x=0.01, ha="left")
    bar_width = 0.8 / len(COMPARISON_ORDER)
    for panel, metric in enumerate(metrics_to_plot):
        ax = axes[0][panel]
        style_axis(ax)
        for slot, (algorithm, source) in enumerate(COMPARISON_ORDER):
            xs = []
            heights = []
            below = []
            above = []
            for index, (_label, variant_stats) in enumerate(variants):
                values = bar_values(variant_stats, algorithm, source, metric)
                if values is None:
                    continue
                xs.append(index - 0.4 + bar_width * (slot + 0.5))
                heights.append(values[0])
                below.append(values[1])
                above.append(values[2])
            if len(xs) == 0:
                continue
            hatch = "///" if source == "mininet" else None
            ax.bar(xs, heights, width=bar_width * 0.9, color=ALGORITHM_COLORS[algorithm],
                   hatch=hatch, edgecolor=SURFACE, linewidth=0.5,
                   label=ALGORITHM_LABELS[algorithm] + " (" + source + ")")
            ax.errorbar(xs, heights, yerr=[below, above], fmt="none",
                        ecolor=TEXT_SECONDARY, elinewidth=1, capsize=2)
        labels = []
        for label, _stats in variants:
            labels.append(label)
        ax.set_xticks(range(len(variants)))
        ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
        ax.set_title(METRIC_TITLES.get(metric, metric), color=TEXT, fontsize=10, loc="left")
    handles, names = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=len(names), frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def plot_goodput_vs_rtt(points, model_lines, link_mbps, path):
    """
    S6 explained: measured goodput against base RTT, with the Mathis formula.
    points: {(algorithm, source): [(rtt_ms, describe), ...]}
    model_lines: {label: [(rtt_ms, mbps), ...]}
    """
    fig, ax = plt.subplots(figsize=(8, 4.6))
    fig.patch.set_facecolor(SURFACE)
    style_axis(ax)
    styles = ["--", ":"]
    index = 0
    for label in model_lines:
        xs = []
        ys = []
        for rtt_ms, mbps in model_lines[label]:
            xs.append(rtt_ms)
            ys.append(mbps)
        ax.plot(xs, ys, styles[index % 2], color=TEXT_SECONDARY, linewidth=1.5,
                label=label + " (model)")
        index = index + 1
    ax.axhline(link_mbps, color=GRID, linewidth=2)
    ax.text(xs[-1], link_mbps, " link " + format_number_short(link_mbps) + " Mbit/s",
            color=TEXT_SECONDARY, fontsize=8, va="bottom", ha="right")
    # Measured points: markers only (only these RTTs were measured, so no
    # lines between them), each series nudged sideways so whiskers do not overlap
    series_index = 0
    for key in points:
        algorithm, source = key
        nudge = 1.0 + 0.035 * (series_index - (len(points) - 1) / 2.0)
        series_index = series_index + 1
        xs = []
        ys = []
        below = []
        above = []
        for rtt_ms, stats in points[key]:
            if stats["n"] == 0:
                continue
            xs.append(rtt_ms * nudge)
            ys.append(stats["mean"])
            below.append(stats["mean"] - stats["min"])
            above.append(stats["max"] - stats["mean"])
        marker = "s" if source == "mininet" else "o"
        ax.errorbar(xs, ys, yerr=[below, above], fmt=marker, color=ALGORITHM_COLORS[algorithm],
                    markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5,
                    elinewidth=1.5, capsize=3,
                    label=ALGORITHM_LABELS[algorithm] + " (" + source + ")")
    ax.set_xscale("log")
    ax.set_xticks([10, 20, 50, 100, 200])
    ax.set_xticklabels(["10", "20", "50", "100", "200"])
    ax.set_xlabel("base RTT (ms), log scale")
    ax.set_ylabel("goodput (Mbit/s)")
    ax.set_title("S6: goodput vs RTT at 0.5 % random loss (mean, min..max)",
                 color=TEXT, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def format_number_short(value):
    if float(value) == int(value):
        return str(int(value))
    return str(value)
