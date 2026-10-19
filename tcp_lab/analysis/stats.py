"""
Mean, median and spread of repeated runs.

Real runs (Mininet) and random-loss simulations (one per seed) give a
different number every time, so every result is reported as:

    n       how many runs / seeds
    mean    the average
    median  the middle value (not pulled by one extreme run)
    std     sample standard deviation (how far runs are from the mean)
    min/max the extremes

Example: S6 rtt_10ms on Mininet had 80, 198 and 786 retransmissions:
mean 354.7, median 198, so one run with a long loss episode pulls the mean
far up. That is why both are shown and why nothing is ranked on one run.
"""

import statistics


def numbers_only(values):
    """Drop missing values (None): a run without that measurement."""
    result = []
    for value in values:
        if value is not None:
            result.append(value)
    return result


def describe(values):
    """Summary of a list of numbers; every field is None for an empty list."""
    values = numbers_only(values)
    if len(values) == 0:
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None}
    if len(values) > 1:
        std = statistics.stdev(values)
    else:
        std = 0.0              # one value: no spread can be measured
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "std": round(std, 4),
        "min": min(values),
        "max": max(values),
    }


def describe_rows(rows, keys):
    """{key: describe(values of that key over all rows)} for the given keys."""
    result = {}
    for key in keys:
        values = []
        for row in rows:
            values.append(row.get(key))
        result[key] = describe(values)
    return result


def format_stats(stats, digits=2):
    """'3.46 (median 3.46, 3.15-3.72, n=3)' for tables."""
    if stats["n"] == 0:
        return "-"
    pattern = "%." + str(digits) + "f"
    text = pattern % stats["mean"]
    if stats["n"] > 1:
        text = (text + " (median " + pattern % stats["median"] + ", "
                + pattern % stats["min"] + "-" + pattern % stats["max"]
                + ", n=" + str(stats["n"]) + ")")
    return text
