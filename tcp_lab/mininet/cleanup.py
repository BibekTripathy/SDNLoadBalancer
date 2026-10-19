"""
Remove what an earlier, crashed TCP lab run left behind.

Why not Mininet's own cleanup (`mn -c` / mininet.clean.cleanup)?
  - it calls the obsolete `egrep` (newer grep prints a warning for it),
  - it removes EVERY OVS bridge and every "*-ethN" link on the machine,
  - it kills every process called ryu-manager, i.e. your controller,
  - it deletes /tmp/*.log.
This version only touches the lab's own switches, links and node shells.

    sudo python3 -m tcp_lab.mininet.cleanup             # dumbbell names
    sudo python3 -m tcp_lab.mininet.cleanup --target vip
"""

import argparse
import subprocess
import sys

DUMBBELL_SWITCHES = ["sw1", "sw2"]
DUMBBELL_HOSTS = ["c1", "c2", "c3", "sv1", "sv2"]

VIP_SWITCHES = ["s1"]
VIP_HOSTS = ["client", "server1", "server2", "server3"]


def names_for(target):
    """(switch names, host names) of one lab topology."""
    if target == "dumbbell":
        return DUMBBELL_SWITCHES, DUMBBELL_HOSTS
    if target == "vip":
        return VIP_SWITCHES, VIP_HOSTS
    raise ValueError("target must be 'dumbbell' or 'vip'")


def build_list_links_command(switches, hosts):
    """
    Shell command that prints the lab's leftover interfaces, one per line.
    `ip -o link show` prints one line per interface: "7: sw1-eth1@if6: <...>".
    grep -E (not the obsolete egrep) keeps "N: <name>-ethK", cut keeps the name.
    """
    pattern = "^[0-9]+: (" + "|".join(switches + hosts) + ")-eth[0-9]+"
    return "ip -o link show | grep -E -o '" + pattern + "' | cut -d' ' -f2"


def build_cleanup_commands(switches, hosts, links):
    """All commands to run, given the leftover links found."""
    commands = []
    for switch in switches:
        commands.append("ovs-vsctl --if-exists del-br " + switch)
    for link in links:
        # Deleting one end of a veth pair removes the other end as well
        commands.append("ip link del " + link + " 2> /dev/null")
    for host in hosts:
        # Every Mininet host is a shell started as "bash ... mininet:<name>"
        commands.append("pkill -9 -f 'mininet:" + host + "$'")
    return commands


def run_shell(command):
    result = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                            text=True, check=False)
    return result.stdout


def cleanup_lab(target="dumbbell", verbose=True):
    switches, hosts = names_for(target)
    links = []
    for line in run_shell(build_list_links_command(switches, hosts)).splitlines():
        if line.strip() != "":
            links.append(line.strip())
    for command in build_cleanup_commands(switches, hosts, links):
        if verbose:
            print("  cleanup: " + command)
        run_shell(command)


def main():
    parser = argparse.ArgumentParser(description="Remove leftovers of a TCP lab run")
    parser.add_argument("--target", choices=["dumbbell", "vip"], default="dumbbell")
    args = parser.parse_args()
    cleanup_lab(args.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
