"""
Write the Phase 5 analysis as a Markdown report (results/analysis/report.md).

Every column header says where its numbers come from:
  (simulator)  Python model, mean over seeds
  (mininet)    real Linux reno with SACK off, mean over runs
  (model)      the Mathis formula
Cells look like "3.46 (median 3.46, 3.15-3.72, n=3)": mean, median,
min-max and how many runs / seeds.
"""

from tcp_lab.analysis import scoring, stats

ALGORITHMS = ["tahoe", "reno", "newreno"]
NAMES = {"tahoe": "Tahoe", "reno": "Reno", "newreno": "New Reno", "linux_reno": "Linux reno"}

TABLE_METRICS = [
    ("goodput_mbps", "goodput (Mbit/s)", 2),
    ("throughput_mbps", "throughput (Mbit/s)", 2),
    ("retransmissions", "retransmissions", 1),
    ("spurious_retransmissions", "  of which spurious", 1),
    ("timeouts", "timeouts", 1),
    ("avg_recovery_s", "avg recovery time (s)", 3),
    ("p95_rtt_ms", "P95 RTT (ms)", 1),
    ("jain_fairness", "Jain fairness", 3),
    ("queue_drops", "queue drops (mininet tc)", 1),
]

METRIC_NAMES = {"goodput_mbps": "goodput", "timeouts": "timeouts",
                "avg_recovery_s": "recovery time", "spurious_retransmissions": "spurious resends",
                "retransmissions": "retransmissions", "p95_rtt_ms": "P95 RTT",
                "jain_fairness": "fairness"}


def cell(variant, source, algorithm, metric, digits):
    group = variant[source]
    if algorithm not in group:
        return "-"
    return stats.format_stats(group[algorithm][metric], digits)


def variant_table(variant):
    lines = []
    header = "| metric |"
    rule = "|---|"
    for algorithm in ALGORITHMS:
        header = header + " " + NAMES[algorithm] + " (simulator) |"
        rule = rule + "---|"
    header = header + " Linux reno (mininet) |"
    rule = rule + "---|"
    lines.append(header)
    lines.append(rule)
    for metric, title, digits in TABLE_METRICS:
        if metric == "jain_fairness" and variant["num_flows"] < 2:
            continue
        line = "| " + title + " |"
        has_value = False
        for algorithm in ALGORITHMS:
            text = cell(variant, "simulator", algorithm, metric, digits)
            if text != "-":
                has_value = True
            line = line + " " + text + " |"
        text = cell(variant, "mininet", "linux_reno", metric, digits)
        if text != "-":
            has_value = True
        line = line + " " + text + " |"
        if has_value:
            lines.append(line)
    return lines


def wins_by_metric(wins, algorithm):
    """{metric: number of clear wins} for one algorithm."""
    counts = {}
    for win in wins:
        if win["winner"] == algorithm:
            counts[win["metric"]] = counts.get(win["metric"], 0) + 1
    return counts


def all_wins(analysis):
    result = []
    for scenario_id in analysis["scenarios"]:
        for item in analysis["scenarios"][scenario_id]["variants"]:
            if "score" in item:
                result.extend(item["score"]["wins"])
    return result


def describe_wins(counts):
    parts = []
    for metric, _better, _weight, _multi in scoring.SCORE_METRICS:
        if metric in counts:
            parts.append(METRIC_NAMES[metric] + " (" + str(counts[metric]) + ")")
    if len(parts) == 0:
        return "no clear wins"
    return ", ".join(parts)


def recommendation_section(analysis):
    rec = analysis["recommendation"]
    lines = ["## Recommendation (from the simulator)", ""]
    if len(rec["overall_points"]) == 0:
        lines.append("No simulator results to score yet.")
        return lines
    ranking = sorted(rec["overall_points"].items(), key=lambda item: -item[1])
    lines.append("| algorithm | points (simulator) | scenarios won | clear wins by metric |")
    lines.append("|---|---|---|---|")
    wins = all_wins(analysis)
    for algorithm, points in ranking:
        lines.append("| " + NAMES[algorithm] + " | " + str(points) + " | "
                     + str(rec["scenarios_won"].get(algorithm, 0)) + " | "
                     + describe_wins(wins_by_metric(wins, algorithm)) + " |")
    lines.append("")
    winners = []
    for algorithm in rec["winners"]:
        winners.append(NAMES[algorithm])
    lines.append("**Recommended: " + " and ".join(winners) + ".** "
                 "Points are only given for a *clear* win: the mean over seeds must be better "
                 "by more than the standard deviation and by at least 2 % (see "
                 "`analysis/scoring.py`), so run-to-run noise cannot decide the ranking.")
    lines.append("")
    if rec["winners"] == ["newreno"]:
        lines.append("Why New Reno: with several losses in one window, Reno leaves fast "
                     "recovery on the first partial ACK and usually ends in a timeout, and "
                     "Tahoe always restarts from cwnd 1 and resends data the receiver already "
                     "has. New Reno stays in fast recovery and repairs one hole per RTT, so it "
                     "avoids most timeouts and spurious resends. With single, isolated losses "
                     "(S1) the three behave the same apart from Tahoe's slow start.")
        lines.append("")
    lines.append("Mininet cannot rank the three (Linux has no Tahoe, and Linux reno without "
                 "SACK *is* a New Reno); it is used below to check the simulator.")
    return lines


def scenario_section(entry):
    lines = ["## " + entry["scenario"] + " - " + entry["name"], "", entry["description"], ""]
    if not entry["has_simulator"]:
        lines.append("_No simulator results: run `python -m tcp_lab.run_sim_scenarios`._")
        lines.append("")
    for item in entry["variants"]:
        counts = []
        if item["seeds"] > 0:
            counts.append("simulator: " + str(item["seeds"]) + " seed(s)")
        if item["mininet_runs"] > 0:
            counts.append("mininet: " + str(item["mininet_runs"]) + " run(s)")
        if len(counts) == 0:
            continue
        lines.append("### " + item["label"] + " (" + ", ".join(counts) + ")")
        lines.append("")
        lines.extend(variant_table(item))
        lines.append("")
        if "score" in item:
            parts = []
            for algorithm in ALGORITHMS:
                if algorithm in item["score"]["points"]:
                    parts.append(NAMES[algorithm] + " " + str(item["score"]["points"][algorithm]))
            lines.append("Score (simulator): " + ", ".join(parts) + ".")
            lines.append("")
    if "points" in entry:
        winners = []
        for algorithm in entry["winners"]:
            winners.append(NAMES[algorithm])
        lines.append("**" + entry["scenario"] + " total (simulator):** "
                     + ", ".join(NAMES[a] + " " + str(entry["points"][a]) for a in ALGORITHMS
                                 if a in entry["points"])
                     + " -> best: " + " / ".join(winners) + ".")
        lines.append("")
    lines.append("![" + entry["scenario"] + "](" + entry["scenario"] + "_comparison.png)")
    lines.append("")
    return lines


def number(value, digits=2):
    if value is None:
        return "-"
    return ("%." + str(digits) + "f") % value


def validation_section(analysis):
    intro = ("Linux reno with SACK off should behave like the simulator's **New Reno**, not "
             "Reno. Linux starts every connection with no ssthresh limit, so it is compared "
             "with simulator runs that start the same way (**Linux-like start**); the normal "
             "simulator runs start with ssthresh 32 and are shown for reference. "
             "Means over runs / seeds:")
    header = ("| variant | goodput: Linux reno (mininet) | New Reno, Linux-like start "
              "(simulator) | Reno, Linux-like start (simulator) | New Reno, ssthresh 32 "
              "(simulator) | Linux vs New Reno (same start) | closer by goodput "
              "| timeouts: Linux / New Reno / Reno | Linux timeouts |")
    lines = ["## Does the simulator match real Linux? (mininet vs simulator)", "",
             intro, "", header, "|---|---|---|---|---|---|---|---|---|"]
    count = 0
    goodput_newreno = 0
    more_timeouts = []
    with_spurious = 0
    for scenario_id in analysis["scenarios"]:
        for item in analysis["scenarios"][scenario_id]["variants"]:
            if "validation" not in item:
                continue
            check = item["validation"]
            if check["closer_by_goodput"] is None:
                continue
            count = count + 1
            if check["closer_by_goodput"] == "newreno":
                goodput_newreno = goodput_newreno + 1
            if check["timeouts_vs_simulator"] == "more than both":
                more_timeouts.append(scenario_id + " " + item["label"])
                if check["mininet_spurious"] is not None and check["mininet_spurious"] > 0:
                    with_spurious = with_spurious + 1
            difference = "-"
            if check["goodput_vs_newreno_linux_start_pct"] is not None:
                difference = "%+.0f %%" % check["goodput_vs_newreno_linux_start_pct"]
            lines.append("| " + scenario_id + " " + item["label"] + " | "
                         + stats.format_stats(check["mininet_goodput"], 2) + " | "
                         + number(check["newreno_linux_start_goodput"]) + " | "
                         + number(check["reno_linux_start_goodput"]) + " | "
                         + number(check["newreno_goodput"]) + " | " + difference + " | "
                         + NAMES.get(check["closer_by_goodput"], "-") + " | "
                         + number(check["mininet_timeouts"], 1) + " / "
                         + number(check["newreno_linux_start_timeouts"], 1) + " / "
                         + number(check["reno_linux_start_timeouts"], 1) + " | "
                         + str(check["timeouts_vs_simulator"]) + " |")
    lines.append("")
    if count == 0:
        lines.append("_No variant has both simulator and Mininet results yet._")
        lines.append("")
        return lines
    lines.append("**Goodput:** of " + str(count) + " variants, Linux is closer to New Reno "
                 "than to Reno in " + str(goodput_newreno) + ".")
    lines.append("")
    if len(more_timeouts) > 0:
        lines.append("**Timeouts:** Linux had more timeouts than *both* simulated algorithms in "
                     + str(len(more_timeouts)) + " of " + str(count) + " variants ("
                     + ", ".join(more_timeouts) + "): on timeouts the simulator is more "
                     "optimistic than real Linux. In " + str(with_spurious) + " of these the "
                     "Mininet runs also have spurious resends. That fits what a timeout does "
                     "without SACK: Linux marks every unacknowledged segment lost and resends "
                     "them all, including ones the receiver already has (seen in detail in "
                     "S3 loss_0.1pct). *Why* Linux reaches a timeout more often is not settled "
                     "by these results; its RTO estimator and recovery details differ from the "
                     "simulator's, and with 3 runs per variant part of the gap may be noise.")
        lines.append("")
    lines.append("Known reasons for the remaining gaps (not bugs): Linux receivers delay ACKs "
                 "(one ACK per two segments), so cwnd grows more slowly in congestion avoidance; "
                 "Linux reduces cwnd gradually during recovery (PRR) instead of Reno's "
                 "inflation; its MSS is 1448 bytes, not 1460; and Mininet has only 3 runs per "
                 "variant, so its means are themselves uncertain (see the min-max).")
    lines.append("")
    return lines


def s6_section(analysis):
    explanation = analysis.get("s6_explanation")
    if explanation is None:
        return []
    lines = ["## Why S6 goodput falls from ~9 to ~3 Mbit/s between 10 and 50 ms RTT", ""]
    lines.append("| base RTT | link needs (BDP, segments) | loss allows (avg window, segments) "
                 "| goodput (model) | New Reno (simulator) | Linux reno (mininet) |")
    lines.append("|---|---|---|---|---|---|")
    for row in explanation["rows"]:
        model = row["model"]
        if model is None:
            continue
        sim_text = "-"
        if "simulator_newreno_goodput" in row:
            sim_text = stats.format_stats(row["simulator_newreno_goodput"], 2)
        mn_text = "-"
        if "mininet_goodput" in row:
            mn_text = stats.format_stats(row["mininet_goodput"], 2)
        lines.append("| %.0f ms | %.0f | %.0f (ACK per segment) / %.0f (delayed ACKs) "
                     "| %.2f / %.2f | %s | %s |"
                     % (model["base_rtt_ms"], model["bdp_segments"],
                        model["loss_window_segments"], model["loss_window_segments_delayed_ack"],
                        model["goodput_sim_style_mbps"], model["goodput_linux_style_mbps"],
                        sim_text, mn_text))
    lines.append("")
    models = []
    for row in explanation["rows"]:
        if row["model"] is not None:
            models.append(row["model"])
    if len(models) >= 2:
        short = models[0]
        longer = models[1]
        lines.append(
            "**The delay (together with the %.1f %% random loss) causes it, not the queue.** "
            "At every loss a Reno-style flow halves its window, and it grows back by one "
            "segment per RTT, so on average it can keep only about C/sqrt(p) segments in "
            "flight: %.0f here (%.0f with Linux's delayed ACKs), *whatever the RTT*. To fill "
            "the link, the window must be at least the bandwidth-delay product (BDP). At %.0f ms "
            "the BDP is %.0f segments, less than the loss allows, so the link stays full. At "
            "%.0f ms the link needs %.0f segments but the loss allows only %.0f-%.0f, so "
            "goodput is about window x MSS / RTT. That is the Mathis formula, "
            "rate = MSS/RTT x C/sqrt(p) (the 'model' column)."
            % (short["loss_rate"] * 100, short["loss_window_segments"],
               short["loss_window_segments_delayed_ack"], short["base_rtt_ms"],
               short["bdp_segments"], longer["base_rtt_ms"], longer["bdp_segments"],
               longer["loss_window_segments_delayed_ack"], longer["loss_window_segments"]))
        lines.append("")
    lines.append(
        "The queue only helps when the window is *larger* than the BDP (then the extra "
        "packets wait in the queue instead of being lost). At 50 ms the window is far below "
        "the BDP, so the queue is almost always empty and its size cannot change goodput.")
    lines.append("")
    if len(explanation["queue_check"]) > 0:
        lines.append("Check (scenario S6Q): same as S6 rtt_50ms, only the queue size or the "
                     "loss changes:")
        lines.append("")
        lines.append("| variant | queue (packets) | random loss | New Reno goodput (simulator) "
                     "| Linux reno goodput (mininet) |")
        lines.append("|---|---|---|---|---|")
        for check in explanation["queue_check"]:
            sim_text = "-"
            if "simulator_newreno_goodput" in check:
                sim_text = stats.format_stats(check["simulator_newreno_goodput"], 2)
            mn_text = "not run yet"
            if "mininet_goodput" in check:
                mn_text = stats.format_stats(check["mininet_goodput"], 2)
            lines.append("| %s | %d | %.1f %% | %s | %s |"
                         % (check["label"], check["queue_packets"], check["loss_rate"] * 100,
                            sim_text, mn_text))
        lines.append("")
        lines.extend(queue_check_sentences(explanation["queue_check"]))
        lines.append("")
    lines.append("**Where the queue does matter on Mininet: the spread between runs.** Linux has "
                 "no initial ssthresh, so unless a random loss stops it early, the first slow "
                 "start doubles cwnd far past BDP + queue and loses a burst of packets from the "
                 "full queue. Without SACK those holes are repaired one per RTT, which takes "
                 "seconds. Per run (mininet):")
    lines.append("")
    lines.append("| variant | run | goodput (Mbit/s) | queue drops | random drops | max cwnd | "
                 "retransmissions |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in explanation["rows"]:
        for run in row.get("mininet_runs", []):
            lines.append("| %s | %d | %s | %s | %s | %s | %s |"
                         % (row["label"], run["run"], run["goodput_mbps"], run["queue_drops"],
                            run["random_drops"], run["max_cwnd"], run["retransmissions"]))
    lines.append("")
    lines.extend(overshoot_sentences(explanation["rows"]))
    lines.append("")
    lines.append("![S6](s6_goodput_vs_rtt.png)")
    lines.append("")
    return lines


def mean_range(check_list, key):
    """(lowest mean, highest mean) of one goodput column over several variants."""
    means = []
    for check in check_list:
        if key in check and check[key]["mean"] is not None:
            means.append(check[key]["mean"])
    if len(means) == 0:
        return None
    return (min(means), max(means))


def queue_check_sentences(queue_check):
    """What the S6Q numbers say, written from the numbers themselves."""
    with_loss = []
    without_loss = []
    for check in queue_check:
        if check["loss_rate"] > 0:
            with_loss.append(check)
        else:
            without_loss.append(check)
    lines = []
    for key, source in [("simulator_newreno_goodput", "simulator"), ("mininet_goodput", "mininet")]:
        span = mean_range(with_loss, key)
        if span is None:
            continue
        sentence = ("%s: with loss, the mean goodput stays between %.2f and %.2f Mbit/s for "
                    "every queue size" % (source, span[0], span[1]))
        no_loss = mean_range(without_loss, key)
        if no_loss is not None:
            sentence = sentence + "; without random loss it is %.2f Mbit/s" % no_loss[1]
        lines.append(sentence + ".")
        lines.append("")
    lines.extend(no_loss_sentences(without_loss))
    return lines


def no_loss_sentences(without_loss):
    """
    Without random loss, why does Linux stay below the simulator? Written only
    when both numbers exist, and from the numbers themselves.
    """
    lines = []
    for check in without_loss:
        if "mininet_goodput" not in check or "simulator_newreno_goodput" not in check:
            continue
        linux = check["mininet_goodput"]["mean"]
        simulated = check["simulator_newreno_goodput"]["mean"]
        if linux is None or simulated is None:
            continue
        text = ("**Without random loss, Linux reaches about %.1f Mbit/s at 50 ms RTT, against "
                "%.2f in the simulator** (New Reno, ssthresh 32). Likely cause: Linux starts "
                "with no ssthresh limit, so its first slow start overshoots far past BDP + queue"
                % (linux, simulated))
        if check.get("mininet_max_cwnd") and check["mininet_max_cwnd"]["mean"] is not None:
            text = text + " (max cwnd %.0f segments" % check["mininet_max_cwnd"]["mean"]
            if check.get("mininet_queue_drops") and check["mininet_queue_drops"]["mean"] is not None:
                text = text + ", %.0f queue drops" % check["mininet_queue_drops"]["mean"]
            text = text + ")"
        text = text + ("; without SACK the holes are then repaired one per RTT")
        if check.get("mininet_max_recovery_s") and check["mininet_max_recovery_s"]["mean"] is not None:
            text = text + (", and the longest recovery lasts %.1f s of the 20 s run"
                           % check["mininet_max_recovery_s"]["mean"])
        text = text + "."
        start = check.get("simulator_newreno_linux_start_goodput")
        if start is not None and start["mean"] is not None:
            text = text + (" The simulator agrees: New Reno started like Linux (no ssthresh "
                           "limit) gets %.2f Mbit/s." % start["mean"])
        lines.append(text)
        lines.append("")
    return lines


def overshoot_sentences(rows):
    """Compare Mininet runs that had queue drops with those that had none."""
    with_drops = []
    without_drops = []
    for row in rows:
        for run in row.get("mininet_runs", []):
            if run["queue_drops"] is None or run["max_cwnd"] is None:
                continue
            if run["queue_drops"] > 0:
                with_drops.append(run)
            else:
                without_drops.append(run)
    if len(with_drops) == 0 or len(without_drops) == 0:
        return []
    lines = []
    for name, group in [("with queue drops", with_drops), ("without queue drops", without_drops)]:
        cwnds = []
        for run in group:
            cwnds.append(run["max_cwnd"])
        lines.append("- runs %s: %d, max cwnd %.0f-%.0f segments"
                     % (name, len(group), min(cwnds), max(cwnds)))
    lines.append("")
    lines.append("So the queue drops come from the first slow start's overshoot. A bigger "
                 "queue makes that one burst bigger. It does not set the overall goodput level, "
                 "which the loss-and-RTT rule above explains.")
    return lines


def build_report(analysis):
    sources = ("Sources: **simulator** = the Python model of Tahoe, Reno and New Reno "
               "(random-loss variants: mean over seeds); **mininet** = real Linux reno with SACK "
               "off (mean over runs; Linux has no Tahoe, and reno without SACK behaves like New "
               "Reno); **model** = the Mathis formula. Cells: mean (median, min-max, n).")
    lines = ["# TCP Lab - analysis (Phase 5)", "", sources, ""]
    lines.extend(recommendation_section(analysis))
    lines.append("")
    lines.extend(validation_section(analysis))
    lines.extend(s6_section(analysis))
    for scenario_id in analysis["scenarios"]:
        lines.extend(scenario_section(analysis["scenarios"][scenario_id]))
    return "\n".join(lines) + "\n"


def console_summary(analysis):
    rec = analysis["recommendation"]
    parts = []
    for algorithm in rec["overall_points"]:
        parts.append(NAMES[algorithm] + " " + str(rec["overall_points"][algorithm]))
    winners = []
    for algorithm in rec["winners"]:
        winners.append(NAMES[algorithm])
    lines = ["Points (simulator): " + ", ".join(parts),
             "Recommended (simulator): " + " / ".join(winners)]
    for scenario_id in analysis["scenarios"]:
        entry = analysis["scenarios"][scenario_id]
        if "winners" in entry:
            names = []
            for algorithm in entry["winners"]:
                names.append(NAMES[algorithm])
            lines.append("  " + scenario_id + ": " + " / ".join(names))
    return "\n".join(lines)
