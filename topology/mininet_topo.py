#!/usr/bin/env python3
"""
Mininet Topology for SDN Dynamic Load Balancer.

Topology Structure:
  - 1 Client (h1): 10.0.0.1 (Switch Port 1)
  - 1 OpenFlow 1.3 OVS Switch (s1)
  - 3 Backend Servers:
      * server1 (h2): 10.0.0.2 (Switch Port 2)
      * server2 (h3): 10.0.0.3 (Switch Port 3)
      * server3 (h4): 10.0.0.4 (Switch Port 4)
  - Remote Ryu Controller: 127.0.0.1:6653
  - Management port mgmt0 on s1: 10.0.0.254 in the ROOT namespace, so the
    controller's health monitor (which runs outside Mininet) can reach the backends.
    Set SDN_MGMT_PORT=0 to skip it.
"""

import os
import shlex
import subprocess
import sys
import time

try:
    from mininet.cli import CLI
    from mininet.link import TCLink
    from mininet.log import info, setLogLevel
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController
    from mininet.topo import Topo
except ImportError:
    print(
        "Warning: Mininet is not installed in the current Python environment or system packages.\n"
        "Please run with system Python or install Mininet system package: sudo apt install mininet (or pacman -S mininet)"
    )
    # Lets the helper functions below be imported (and unit-tested) without Mininet
    Topo = object


class LoadBalancerTopo(Topo):
    """Custom topology with 1 client, 1 OVS switch, and 3 backend servers."""

    def build(self):
        # Add single OpenFlow switch
        s1 = self.addSwitch("s1", protocols="OpenFlow13")

        # Add client host (Port 1)
        client = self.addHost(
            "client",
            ip="10.0.0.1/24",
            mac="00:00:00:00:00:01",
            defaultRoute="via 10.0.0.100",
        )
        self.addLink(client, s1, port1=0, port2=1)

        # Add 3 backend servers
        servers = [
            ("server1", "10.0.0.2/24", "00:00:00:00:00:02", 2),
            ("server2", "10.0.0.3/24", "00:00:00:00:00:03", 3),
            ("server3", "10.0.0.4/24", "00:00:00:00:00:04", 4),
        ]

        for name, ip, mac, sw_port in servers:
            host = self.addHost(name, ip=ip, mac=mac)
            self.addLink(host, s1, port1=0, port2=sw_port)


# Absolute paths, so the script works whatever directory it is started from
TOPOLOGY_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOPOLOGY_DIR)
SERVER_APP = os.path.join(TOPOLOGY_DIR, "server_app.py")

BACKEND_NAMES = ["server1", "server2", "server3"]
BACKEND_PORT = 80


def pick_python():
    """The project venv's Python if there is one (local runs), else the Python running this script (Docker image)."""
    venv_python = os.path.join(REPO_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_python) and os.access(venv_python, os.X_OK):
        return venv_python
    return sys.executable


def server_command(name, port=BACKEND_PORT, python=None):
    """Shell command that starts one backend in the background, logging to /tmp/<name>.log."""
    if python is None:
        python = pick_python()
    # -u: unbuffered output, so the log already has the error if the server dies at once
    return (
        f"{shlex.quote(python)} -u {shlex.quote(SERVER_APP)} --name {name} --port {port}"
        f" > /tmp/{name}.log 2>&1 &"
    )


def is_listening(ss_output, port):
    """True if `ss -ltnH` output has a socket listening on the given TCP port."""
    for line in ss_output.splitlines():
        fields = line.split()
        # Columns: State Recv-Q Send-Q Local-Address:Port Peer-Address:Port
        if len(fields) < 4 or fields[0] != "LISTEN":
            continue
        if fields[3].rsplit(":", 1)[-1] == str(port):
            return True
    return False


def wait_until_listening(node, port=BACKEND_PORT, timeout=5.0):
    """Poll the host's own network namespace until something listens on the port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_listening(node.cmd("ss -ltnH"), port):
            return True
        time.sleep(0.2)
    return False


def start_backends(net):
    """Start server_app.py on every backend host and check each one is listening."""
    python = pick_python()
    info(f"*** Starting HTTP servers on backend hosts with {python}\n")
    for s_name in BACKEND_NAMES:
        server_node = net.get(s_name)
        server_node.cmd(server_command(s_name, BACKEND_PORT, python))

    all_ok = True
    for s_name in BACKEND_NAMES:
        server_node = net.get(s_name)
        if wait_until_listening(server_node, BACKEND_PORT):
            info(f"*** HTTP server on {s_name} is listening on {server_node.IP()}:{BACKEND_PORT}\n")
        else:
            all_ok = False
            log_tail = server_node.cmd(f"tail -n 20 /tmp/{s_name}.log")
            info(
                f"*** ERROR: HTTP server on {s_name} ({server_node.IP()}:{BACKEND_PORT}) is not listening.\n"
                f"*** Last lines of /tmp/{s_name}.log:\n{log_tail}\n"
            )
    return all_ok


# Management port: an OVS internal port on s1 whose end lives in the root namespace
MGMT_PORT = "mgmt0"
MGMT_IP = "10.0.0.254"
MGMT_PREFIX = 24
MGMT_MAC = "00:00:00:00:00:fe"
# Fixed OpenFlow port number, far above the 2-254 range the API gives backends
MGMT_OFPORT = 1000


def run_root(command):
    """Run a shell command in the root namespace; returns (exit code, output)."""
    result = subprocess.run(
        ["/bin/sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    return result.returncode, result.stdout


def find_subnet_conflict(ip_addr_output, port=MGMT_PORT):
    """
    Name of another interface that already has a 10.0.0.x address, else None.
    Input is `ip -o -4 addr show`: "2: wlan0    inet 10.0.0.37/24 brd ... ".
    On such a machine (e.g. a 10.0.0.0/24 home LAN) we must not add the port.
    """
    for line in ip_addr_output.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[2] != "inet":
            continue
        name = fields[1].split("@")[0]
        if name != port and fields[3].startswith("10.0.0."):
            return name
    return None


def mgmt_add_command(bridge="s1"):
    """ovs-vsctl command that adds the management port (no-op if it is already there)."""
    return (
        f"ovs-vsctl --may-exist add-port {bridge} {MGMT_PORT}"
        f" -- set interface {MGMT_PORT} type=internal ofport_request={MGMT_OFPORT}"
        f' mac=\\"{MGMT_MAC}\\"'
    )


def mgmt_address_commands():
    """Give the port its address and bring it up; both are safe to repeat."""
    return [
        f"ip addr replace {MGMT_IP}/{MGMT_PREFIX} dev {MGMT_PORT}",
        f"ip link set {MGMT_PORT} up",
    ]


def add_mgmt_port(bridge="s1"):
    """Add mgmt0 (10.0.0.254) to the bridge, only if it is missing. Returns True if it is up."""
    if os.environ.get("SDN_MGMT_PORT", "1") == "0":
        info("*** SDN_MGMT_PORT=0: no management port, health checks cannot reach the backends\n")
        return False

    _, addresses = run_root("ip -o -4 addr show")
    conflict = find_subnet_conflict(addresses)
    if conflict is not None:
        info(
            f"*** WARNING: {conflict} already has a 10.0.0.x address; not adding {MGMT_PORT}"
            f" ({MGMT_IP}) so this machine's own network keeps working\n"
        )
        return False

    code, owner = run_root(f"ovs-vsctl port-to-br {MGMT_PORT}")
    if code == 0 and owner.strip() == bridge:
        info(f"*** {MGMT_PORT} is already on {bridge}\n")
    elif run_root(f"ip link show {MGMT_PORT}")[0] == 0:
        info(f"*** WARNING: an interface called {MGMT_PORT} exists but is not on {bridge}; leaving it alone\n")
        return False
    else:
        code, output = run_root(mgmt_add_command(bridge))
        if code != 0:
            info(f"*** ERROR: could not add {MGMT_PORT} to {bridge}:\n{output}\n")
            return False

    for command in mgmt_address_commands():
        code, output = run_root(command)
        if code != 0:
            info(f"*** ERROR: '{command}' failed:\n{output}\n")
            return False
    info(f"*** Management port {MGMT_PORT} is up: {MGMT_IP}/{MGMT_PREFIX} in the root namespace\n")
    return True


def remove_mgmt_port(bridge="s1"):
    """Remove the management port (no-op if it is not there)."""
    run_root(f"ovs-vsctl --if-exists del-port {bridge} {MGMT_PORT}")


def run_topology(controller_ip: str = "127.0.0.1", controller_port: int = 6653):
    """Starts the Mininet network and spawns backend HTTP servers."""
    setLogLevel("info")

    topo = LoadBalancerTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=None,
        autoSetMacs=False,
        autoStaticArp=False,
    )

    info(f"*** Adding Remote Ryu Controller at {controller_ip}:{controller_port}\n")
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port,
    )

    info("*** Starting Network\n")
    net.start()

    # Set switch protocols to OpenFlow 1.3 explicitly
    s1 = net.get("s1")
    s1.cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")

    try:
        add_mgmt_port("s1")
        start_backends(net)

        info("*** Network is ready. Use 'pingall' or 'client curl 10.0.0.100' to test.\n")
        CLI(net)
    finally:
        info("*** Stopping Network\n")
        remove_mgmt_port("s1")
        net.stop()


if __name__ == "__main__":
    run_topology()
