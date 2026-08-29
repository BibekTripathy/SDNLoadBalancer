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

    info("*** Starting HTTP servers on backend hosts\n")
    for s_name in ["server1", "server2", "server3"]:
        server_node = net.get(s_name)
        server_node.cmd(
            f"$(pwd)/.venv/bin/python topology/server_app.py --name {s_name} --port 80 > /tmp/{s_name}.log 2>&1 &"
        )
        info(f"*** Started HTTP server on {s_name} (10.0.0.{s_name[-1]}:80)\n")

    info("*** Network is ready. Use 'pingall' or 'client curl 10.0.0.100' to test.\n")
    CLI(net)

    info("*** Stopping Network\n")
    net.stop()


if __name__ == "__main__":
    run_topology()
