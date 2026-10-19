r"""
Change the bottleneck link conditions while an experiment is running.

On the bottleneck interface we build this queueing tree:

    root 1:   netem   - propagation delay (+ jitter) and packet loss
      \- 10:  tbf     - bandwidth limit (token bucket) and the drop-tail queue

This is the recipe from the Linux netem documentation for "delay + rate".
Packets wait in netem for the delay, then go into tbf, which sends them at
`rate_mbps`. tbf's `limit` (in bytes) is the bottleneck queue: when it is
full, new packets are dropped (drop-tail), just like in the simulator.
netem gets a big limit (10000 packets) so it never drops by itself.

`tc qdisc replace` changes a qdisc in place when it already exists, so the
same two commands are used for the first setup and for every later change
(queued packets are kept).

Link conditions are a plain dict:
    {
      "rate_mbps": 10,        # None = no bandwidth limit (no tbf)
      "delay_ms": 10,         # one-way delay added on this interface
      "jitter_ms": 0,
      "loss_pct": 0,          # random (independent) loss
      "burst_loss": None,     # or {"p_pct": 1, "r_pct": 25}, see below
      "queue_packets": 100,   # tbf queue size in full-size packets
      "seed": None,           # netem random seed; None = netem picks one
    }

Burst loss uses netem's Gilbert-Elliott model ("loss gemodel p r"):
the link is either GOOD (no loss) or BAD (every packet lost).
  p = chance per packet to go GOOD -> BAD
  r = chance per packet to go BAD -> GOOD   (mean burst = 1/r packets)
  long-run loss rate = p / (p + r)

Seed: netem draws its random losses from its own random generator. Giving
it "seed N" (Linux 6.4+ / iproute2 6.5+) makes the loss pattern of run N
repeatable, while runs with different seeds see different patterns. That
is what we want when an experiment is repeated and averaged.
"""

import time

PACKET_BYTES = 1514          # Ethernet frame of a full 1448-byte TCP segment (+ headers)
NETEM_LIMIT_PACKETS = 10000


def default_conditions():
    return {
        "rate_mbps": 10.0,
        "delay_ms": 10.0,
        "jitter_ms": 0.0,
        "loss_pct": 0.0,
        "burst_loss": None,
        "queue_packets": 100,
        "seed": None,
    }


def merged_conditions(base, changes):
    """Copy of `base` with the keys in `changes` replaced."""
    result = dict(base)
    for key in changes:
        result[key] = changes[key]
    return result


def format_number(value):
    """10.0 -> '10', 2.5 -> '2.5' (tc accepts both, this just reads nicer)."""
    if float(value) == int(value):
        return str(int(value))
    return str(value)


def tbf_burst_bytes(rate_mbps):
    """
    The token bucket must hold at least one packet, and enough for about
    10 ms of traffic at this rate, or tbf cannot reach the configured rate.
    (If one packet is bigger than the bucket, tbf can never send it: keep
    the interface MTU at 1500, which is the Mininet default.)
    """
    ten_ms_of_data = int(rate_mbps * 1e6 / 8 / 100)
    minimum = 10 * PACKET_BYTES
    if ten_ms_of_data < minimum:
        return minimum
    return ten_ms_of_data


def build_netem_command(interface, conditions):
    command = ("tc qdisc replace dev " + interface + " root handle 1: netem limit "
               + str(NETEM_LIMIT_PACKETS))
    command = command + " delay " + format_number(conditions["delay_ms"]) + "ms"
    if conditions["jitter_ms"] > 0:
        command = command + " " + format_number(conditions["jitter_ms"]) + "ms"

    burst = conditions["burst_loss"]
    if burst is not None:
        # Burst (correlated) loss: Gilbert-Elliott model
        command = (command + " loss gemodel " + format_number(burst["p_pct"]) + "% "
                   + format_number(burst["r_pct"]) + "%")
    elif conditions["loss_pct"] > 0:
        # Independent random loss
        command = command + " loss random " + format_number(conditions["loss_pct"]) + "%"
    # .get(): condition dicts written before "seed" existed still work
    if conditions.get("seed") is not None:
        command = command + " seed " + str(conditions["seed"])
    return command


def build_tbf_command(interface, conditions):
    rate = conditions["rate_mbps"]
    queue_bytes = conditions["queue_packets"] * PACKET_BYTES
    return ("tc qdisc replace dev " + interface + " parent 1:1 handle 10: tbf rate "
            + format_number(rate) + "mbit burst " + str(tbf_burst_bytes(rate))
            + " limit " + str(queue_bytes))


def build_tc_commands(interface, conditions):
    """All commands needed to put `conditions` on `interface`."""
    commands = [build_netem_command(interface, conditions)]
    if conditions["rate_mbps"] is not None:
        commands.append(build_tbf_command(interface, conditions))
    return commands


def build_clear_command(interface):
    return "tc qdisc del dev " + interface + " root"


def build_stats_command(interface):
    return "tc -s qdisc show dev " + interface


def parse_tc_stats(text):
    """
    Parse `tc -s qdisc show` output into one dict per qdisc:
        qdisc netem 1: root refcnt 2 limit 10000 delay 10ms
         Sent 1234 bytes 10 pkt (dropped 2, overlimits 0 requeues 0)
         backlog 0b 0p requeues 0
    """
    qdiscs = []
    current = None
    for line in text.splitlines():
        words = line.split()
        if len(words) == 0:
            continue
        if words[0] == "qdisc":
            current = {"kind": words[1], "handle": words[2], "sent_bytes": 0,
                       "sent_packets": 0, "dropped": 0, "overlimits": 0,
                       "backlog_packets": 0}
            qdiscs.append(current)
        elif words[0] == "Sent" and current is not None:
            # Sent <bytes> bytes <pkts> pkt (dropped <n>, overlimits <m> requeues <k>)
            current["sent_bytes"] = int(words[1])
            current["sent_packets"] = int(words[3])
            current["dropped"] = int(words[6].rstrip(","))
            current["overlimits"] = int(words[8])
        elif words[0] == "backlog" and current is not None:
            current["backlog_packets"] = int(words[2].rstrip("p"))
    return qdiscs


# ---------------------------------------------------------------------------
# Running the commands
# ---------------------------------------------------------------------------
def apply_conditions(node, interface, conditions):
    """Run the tc commands on a Mininet node. Raises if tc reports an error."""
    for command in build_tc_commands(interface, conditions):
        output = node.cmd(command)
        if "Error" in output or "RTNETLINK" in output:
            raise RuntimeError("tc failed: " + command + "\n" + output)


def run_timeline(node, interface, timeline, start_time, log=None):
    """
    Apply a list of timed changes, e.g. a bandwidth step down and up:
        [{"time": 10.0, "conditions": {...}}, {"time": 20.0, "conditions": {...}}]
    Times are seconds after `start_time` (a time.time() value).
    Meant to run in its own thread while the traffic is flowing.
    """
    for step in timeline:
        wait = start_time + step["time"] - time.time()
        if wait > 0:
            time.sleep(wait)
        apply_conditions(node, interface, step["conditions"])
        if log is not None:
            log.append({"time": round(time.time() - start_time, 3),
                        "interface": interface, "conditions": step["conditions"]})
