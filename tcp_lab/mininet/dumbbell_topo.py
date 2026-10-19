r"""
Mininet topologies for the TCP lab.

1) DUMBBELL (separate from the load-balancer topology)

    c1 (10.0.0.11) --\                                  /-- sv1 (10.0.0.21)
    c2 (10.0.0.12) ----- sw1 ====== bottleneck ====== sw2
    c3 (10.0.0.13) --/   port 1      (TCLink)    port 1 \-- sv2 (10.0.0.22)

   - Access links are plain (fast, no shaping).
   - sw1-eth1 <-> sw2-eth1 is the bottleneck, created as a TCLink with
     bw / delay / loss / max_queue_size. During an experiment tc_controller
     replaces its qdiscs to change conditions at runtime.
   - Data flows client -> server, so the FORWARD bottleneck queue is the
     egress of sw1-eth1. ACKs come back through sw2-eth1.
   - Switches are called sw1/sw2 (not s1) so the dashboard API, which looks
     for a bridge named "s1", does not mistake this for the LB network.
   - Forwarding: by default OVS runs in "standalone" mode (a normal learning
     switch, no controller needed). With controller="ryu" the switches
     connect to a Ryu controller instead (the project's controller.app does
     plain L2 learning for non-VIP traffic, so it works too).

2) VIP MODE: the project's own load-balancer topology (topology/mininet_topo.py)
   built without its CLI, so clients can send TCP/UDP to the VIP 10.0.0.100
   through the running Ryu load balancer. There is no dedicated bottleneck
   link there, so the tc conditions go on the switch ports towards the
   three servers (data direction) and towards the client (ACK direction).

Requires root and Mininet (run with sudo python3).
"""

from functools import partial

from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo

from tcp_lab.mininet.hosts import CLIENTS, SERVERS

FORWARD_BOTTLENECK = ("sw1", "sw1-eth1")   # carries data (client -> server)
REVERSE_BOTTLENECK = ("sw2", "sw2-eth1")   # carries ACKs (server -> client)

VIP = "10.0.0.100"


class DumbbellTopo(Topo):
    def build(self, bw_mbps=10, delay_ms=10, loss_pct=0, queue_packets=100):
        sw1 = self.addSwitch("sw1")
        sw2 = self.addSwitch("sw2")

        # The bottleneck: port 1 on both switches
        self.addLink(sw1, sw2, port1=1, port2=1, cls=TCLink,
                     bw=bw_mbps, delay=str(delay_ms) + "ms", loss=loss_pct,
                     max_queue_size=queue_packets)

        port = 2
        for name, ip in CLIENTS:
            host = self.addHost(name, ip=ip + "/24")
            self.addLink(host, sw1, port2=port)
            port = port + 1

        port = 2
        for name, ip in SERVERS:
            host = self.addHost(name, ip=ip + "/24")
            self.addLink(host, sw2, port2=port)
            port = port + 1


def build_dumbbell_net(controller="standalone", controller_ip="127.0.0.1",
                       controller_port=6653, **link_options):
    """Create (but do not start) the dumbbell network."""
    topo = DumbbellTopo(**link_options)
    if controller == "standalone":
        # OVS acts as an ordinary learning switch, no OpenFlow controller
        switch = partial(OVSSwitch, failMode="standalone")
        net = Mininet(topo=topo, switch=switch, controller=None, autoSetMacs=True)
    elif controller == "ryu":
        switch = partial(OVSSwitch, protocols="OpenFlow13")
        net = Mininet(topo=topo, switch=switch, controller=None, autoSetMacs=True)
        net.addController("c0", controller=RemoteController,
                          ip=controller_ip, port=controller_port)
    else:
        raise ValueError("controller must be 'standalone' or 'ryu'")
    return net


def dumbbell_info():
    """Names and addresses the experiment scripts need."""
    clients = []
    for name, ip in CLIENTS:
        clients.append({"name": name, "ip": ip})
    servers = []
    for name, ip in SERVERS:
        servers.append({"name": name, "ip": ip})
    return {
        "target": "dumbbell",
        "clients": clients,
        "servers": servers,
        # (switch name, interface) where tc shapes data and ACK traffic
        "forward_interfaces": [FORWARD_BOTTLENECK],
        "reverse_interfaces": [REVERSE_BOTTLENECK],
        "capture_interface_after_bottleneck": ("sw2", "sw2-eth1"),
    }


def build_vip_net(controller_ip="127.0.0.1", controller_port=6653):
    """The load-balancer topology from topology/mininet_topo.py, without its CLI."""
    from topology.mininet_topo import LoadBalancerTopo

    net = Mininet(topo=LoadBalancerTopo(), switch=OVSSwitch, controller=None,
                  autoSetMacs=False, autoStaticArp=False)
    net.addController("c0", controller=RemoteController,
                      ip=controller_ip, port=controller_port)
    return net


def vip_info():
    return {
        "target": "vip",
        "clients": [{"name": "client", "ip": "10.0.0.1"}],
        "servers": [{"name": "server1", "ip": "10.0.0.2"},
                    {"name": "server2", "ip": "10.0.0.3"},
                    {"name": "server3", "ip": "10.0.0.4"}],
        "target_ip": VIP,
        # s1 port 1 = client, ports 2-4 = servers (see topology/mininet_topo.py)
        "forward_interfaces": [("s1", "s1-eth2"), ("s1", "s1-eth3"), ("s1", "s1-eth4")],
        "reverse_interfaces": [("s1", "s1-eth1")],
        "capture_interface_after_bottleneck": None,
    }


def start_vip_net(net):
    """Start the LB network the same way topology/mininet_topo.py does."""
    net.start()
    net.get("s1").cmd("ovs-vsctl set bridge s1 protocols=OpenFlow13")
