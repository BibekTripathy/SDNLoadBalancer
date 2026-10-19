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
"""

import os
import shlex
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

    start_backends(net)

    info("*** Network is ready. Use 'pingall' or 'client curl 10.0.0.100' to test.\n")
    CLI(net)

    info("*** Stopping Network\n")
    net.stop()


if __name__ == "__main__":
    run_topology()
