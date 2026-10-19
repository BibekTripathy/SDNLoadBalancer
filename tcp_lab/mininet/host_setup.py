"""
Prepare Mininet hosts so Linux TCP behaves like the textbook algorithms.

Each Mininet host has its own network namespace, so these settings are
applied inside every host separately and do not touch the real machine
(except the ethtool calls on switch ports, which live in the root namespace).

The command builders return plain lists of strings so they can be unit
tested without Mininet. prepare_host() runs them on a Mininet host.
"""

# (sysctl name, value, why)
SYSCTL_SETTINGS = [
    ("net.ipv4.tcp_congestion_control", "reno",
     "Linux 'reno' = slow start + congestion avoidance + fast retransmit/recovery"),
    ("net.ipv4.tcp_sack", "0",
     "no SACK -> recovery uses partial ACKs, i.e. New Reno (RFC 6582) behaviour"),
    ("net.ipv4.tcp_dsack", "0",
     "no duplicate-SACK either"),
    ("net.ipv4.tcp_no_metrics_save", "1",
     "do not start a new connection with cwnd/ssthresh cached from the last one"),
    ("net.ipv4.tcp_early_retrans", "0",
     "no Tail Loss Probe: losses are found only by dup ACKs or the RTO"),
    ("net.ipv4.tcp_recovery", "0",
     "no RACK time-based loss detection (classic 3 dup ACK rule only)"),
    ("net.ipv4.tcp_frto", "0",
     "no F-RTO: a timeout always resets cwnd, never 'undone'"),
    ("net.ipv4.tcp_ecn", "0",
     "no ECN: congestion is signalled only by packet loss"),
]

# Offloads that would merge many segments into one big packet. With them on,
# tcpdump and ss would show 64 KB "segments" instead of real 1448-byte ones.
OFFLOAD_FEATURES = ["tso", "gso", "gro"]


def build_sysctl_commands():
    commands = []
    for name, value, _why in SYSCTL_SETTINGS:
        commands.append("sysctl -w " + name + "=" + value)
    return commands


def build_offload_commands(interface):
    """ethtool -K <intf> tso off gso off gro off"""
    command = "ethtool -K " + interface
    for feature in OFFLOAD_FEATURES:
        command = command + " " + feature + " off"
    return [command]


def build_initcwnd_commands(route_lines, initcwnd):
    """
    Re-write every route with "initcwnd N" so a new connection starts with
    cwnd = N segments (Linux default is 10). N = 1 makes slow start visible.

    route_lines: output lines of `ip route show`, e.g.
        "10.0.0.0/24 dev c1-eth0 proto kernel scope link src 10.0.0.11"
    """
    commands = []
    for line in route_lines:
        line = line.strip()
        if line == "":
            continue
        # Remove an old "initcwnd X" so we never write it twice
        words = line.split()
        cleaned = []
        skip_next = False
        for word in words:
            if skip_next:
                skip_next = False
                continue
            if word == "initcwnd":
                skip_next = True
                continue
            cleaned.append(word)
        commands.append("ip route change " + " ".join(cleaned) + " initcwnd " + str(initcwnd))
    return commands


# Mininet runs host commands on a terminal (a pty), and newer iproute2 then
# COLOURS its output: "\x1b[1;35m10.0.0.0/24 \x1b[0mdev ...". Feeding that back
# into `ip route change` fails silently. Piping through `cat` means ip is not
# writing to a terminal, so it prints plain text.
ROUTE_SHOW_CMD = "ip route show | cat"


def check_initcwnd(route_lines, initcwnd):
    """Every route should now say 'initcwnd N'. Returns a list of problems."""
    problems = []
    wanted = "initcwnd " + str(initcwnd)
    for line in route_lines:
        line = line.strip()
        if line == "":
            continue
        if wanted not in line:
            problems.append("route without " + wanted + ": " + line)
    return problems


def build_verify_command():
    names = []
    for name, _value, _why in SYSCTL_SETTINGS:
        names.append(name)
    return "sysctl " + " ".join(names)


def parse_sysctl_output(text):
    """'net.ipv4.tcp_sack = 0' lines -> {'net.ipv4.tcp_sack': '0'}"""
    values = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip()
    return values


def check_settings(values):
    """Return a list of problems (empty list = everything is set correctly)."""
    problems = []
    for name, wanted, _why in SYSCTL_SETTINGS:
        actual = values.get(name)
        if actual is None:
            problems.append(name + " is missing (old kernel?)")
        elif actual != wanted:
            problems.append(name + " = " + actual + " (wanted " + wanted + ")")
    return problems


# ---------------------------------------------------------------------------
# Running the commands on Mininet nodes
# ---------------------------------------------------------------------------
def prepare_host(host, initcwnd=None):
    """Apply sysctls, turn offloads off, optionally set initcwnd. Returns problems found."""
    for command in build_sysctl_commands():
        host.cmd(command)
    for interface in host.intfNames():
        if interface == "lo":
            continue
        for command in build_offload_commands(interface):
            host.cmd(command)
    problems = []
    if initcwnd is not None:
        routes = host.cmd(ROUTE_SHOW_CMD).splitlines()
        for command in build_initcwnd_commands(routes, initcwnd):
            host.cmd(command)
        # Read the routes again: did the change really happen?
        problems = check_initcwnd(host.cmd(ROUTE_SHOW_CMD).splitlines(), initcwnd)
    values = parse_sysctl_output(host.cmd(build_verify_command()))
    return check_settings(values) + problems


def disable_switch_offloads(switch):
    """Switch ports are in the root namespace: turn GRO/TSO/GSO off there too."""
    for interface in switch.intfNames():
        if interface == "lo":
            continue
        for command in build_offload_commands(interface):
            switch.cmd(command)
