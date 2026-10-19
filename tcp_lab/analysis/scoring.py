"""
Score Tahoe, Reno and New Reno (SIMULATOR results only) and recommend one.

Linux has no Tahoe, so the three-way comparison can only come from the
simulator. Mininet (linux_reno) is used to check the simulator, not to score.

The rule, in plain words
------------------------
For every variant (e.g. S3 loss_1pct) and every metric below, algorithm A
"clearly beats" algorithm B when A's MEAN over the seeds is better than
B's by more than the noise:

    margin = max(std of A, std of B, 2 % of the larger mean)
    A clearly beats B  <=>  A is better than B by more than `margin`

The 2 % part matters for scenarios without randomness (std = 0), so a
difference of 9.45 vs 9.44 Mbps does not count as a win.

Points for A on one metric = weight x (number of algorithms A clearly beats).
A variant's score is the sum over the metrics; a scenario's score is the sum
over its variants, and the overall score the sum over all scenarios. Ties
(nobody clearly better) give nobody points, so noise cannot decide a ranking.

Weights: goodput matters most (it is what the user gets); timeouts and
recovery time next (they are what the three algorithms differ in);
then wasted resends, delay and fairness.
"""

# (metric, "higher" or "lower" is better, weight, only for several flows?)
SCORE_METRICS = [
    ("goodput_mbps", "higher", 3, False),
    ("timeouts", "lower", 2, False),
    ("avg_recovery_s", "lower", 2, False),
    ("spurious_retransmissions", "lower", 1, False),
    ("retransmissions", "lower", 1, False),
    ("p95_rtt_ms", "lower", 1, False),
    ("jain_fairness", "higher", 1, True),
]

RELATIVE_MARGIN = 0.02     # "2 % of the larger mean"


def clearly_better(stats_a, stats_b, better):
    """True if A's mean beats B's mean by more than the noise margin."""
    if stats_a["n"] == 0 or stats_b["n"] == 0:
        return False
    mean_a = stats_a["mean"]
    mean_b = stats_b["mean"]
    margin = max(stats_a["std"], stats_b["std"],
                 RELATIVE_MARGIN * max(abs(mean_a), abs(mean_b)))
    if better == "higher":
        return mean_a - mean_b > margin
    return mean_b - mean_a > margin


def score_variant(stats_by_algorithm, num_flows):
    """
    stats_by_algorithm: {"tahoe": {metric: describe(...)}, "reno": ..., ...}
    Returns {"points": {algorithm: total}, "wins": [explanations]}.
    """
    algorithms = list(stats_by_algorithm.keys())
    points = {}
    for algorithm in algorithms:
        points[algorithm] = 0
    wins = []
    for metric, better, weight, multi_flow_only in SCORE_METRICS:
        if multi_flow_only and num_flows < 2:
            continue
        for a in algorithms:
            for b in algorithms:
                if a == b:
                    continue
                if clearly_better(stats_by_algorithm[a][metric],
                                  stats_by_algorithm[b][metric], better):
                    points[a] = points[a] + weight
                    wins.append({"metric": metric, "winner": a, "loser": b,
                                 "winner_mean": stats_by_algorithm[a][metric]["mean"],
                                 "loser_mean": stats_by_algorithm[b][metric]["mean"],
                                 "weight": weight})
    return {"points": points, "wins": wins}


def best_of(points):
    """Algorithms with the highest points (a list: there can be a tie)."""
    best = []
    best_points = None
    for algorithm in points:
        if best_points is None or points[algorithm] > best_points:
            best = [algorithm]
            best_points = points[algorithm]
        elif points[algorithm] == best_points:
            best.append(algorithm)
    return best


def add_points(total, points):
    for algorithm in points:
        total[algorithm] = total.get(algorithm, 0) + points[algorithm]


def recommend(scenario_scores):
    """
    scenario_scores: {scenario_id: {"points": {...}, "winners": [...]}}
    Returns the overall winner(s), the overall points and how many
    scenarios each algorithm won (alone or shared).
    """
    overall = {}
    scenarios_won = {}
    for scenario_id in scenario_scores:
        add_points(overall, scenario_scores[scenario_id]["points"])
        for algorithm in scenario_scores[scenario_id]["winners"]:
            scenarios_won[algorithm] = scenarios_won.get(algorithm, 0) + 1
    return {"overall_points": overall, "winners": best_of(overall),
            "scenarios_won": scenarios_won}
