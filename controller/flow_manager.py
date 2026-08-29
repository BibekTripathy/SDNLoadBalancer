"""
OpenFlow 1.3 Flow Manager for SDN Load Balancer.

Handles flow table manipulation, table-miss entry installation, and bidirectional
NAT (IP/MAC address rewrite) flow rules between Client and Backend Servers.
"""

import logging
from typing import Any, Dict, Optional

from ryu.ofproto import ether, inet, ofproto_v1_3
from ryu.ofproto.ofproto_v1_3_parser import (
    OFPActionOutput,
    OFPActionSetField,
    OFPInstructionActions,
    OFPMatch,
)

from controller.config import CONFIG, BackendServer

logger = logging.getLogger(__name__)


class FlowManager:
    """Manages OpenFlow 1.3 flow rule generation and installation on OVS switches."""

    def __init__(self, datapath: Any):
        self.datapath = datapath
        self.ofproto = datapath.ofproto
        self.parser = datapath.ofproto_parser

    def add_flow(
        self,
        match: OFPMatch,
        actions: list,
        priority: int,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
        buffer_id: Optional[int] = None,
    ) -> None:
        """Installs an OpenFlow entry with specified match criteria and actions."""
        inst = [
            self.parser.OFPInstructionActions(
                self.ofproto.OFPIT_APPLY_ACTIONS, actions
            )
        ]
        
        kwargs = {
            "datapath": self.datapath,
            "priority": priority,
            "match": match,
            "instructions": inst,
            "idle_timeout": idle_timeout,
            "hard_timeout": hard_timeout,
        }
        if buffer_id is not None and buffer_id != self.ofproto.OFP_NO_BUFFER:
            kwargs["buffer_id"] = buffer_id

        mod = self.parser.OFPFlowMod(**kwargs)
        self.datapath.send_msg(mod)

    def install_table_miss_flow(self) -> None:
        """Installs default table-miss rule (send unhandled packets to controller)."""
        match = self.parser.OFPMatch()
        actions = [
            self.parser.OFPActionOutput(
                self.ofproto.OFPP_CONTROLLER, self.ofproto.OFPCML_NO_BUFFER
            )
        ]
        self.add_flow(
            match=match,
            actions=actions,
            priority=CONFIG.PRIORITY_TABLE_MISS,
            idle_timeout=0,
            hard_timeout=0,
        )
        logger.info(f"Installed table-miss flow for datapath {self.datapath.id}")

    def install_lb_flows(
        self,
        client_ip: str,
        client_port: int,
        server: BackendServer,
        protocol: int = inet.IPPROTO_TCP,
        idle_timeout: int = CONFIG.IDLE_TIMEOUT,
        hard_timeout: int = CONFIG.HARD_TIMEOUT,
    ) -> None:
        """
        Installs bidirectional NAT OpenFlow rules:
        1. Forward Flow (Client -> VIP:Port):
           - Match: IPv4, Protocol, Source IP=client_ip, Source Port=client_port, Dest IP=VIRTUAL_IP
           - Action: Set Dest MAC = server.mac, Set Dest IP = server.ip, Output -> server.switch_port
        2. Reverse Flow (Backend Server -> Client:Port):
           - Match: IPv4, Protocol, Source IP=server.ip, Dest IP=client_ip, Dest Port=client_port
           - Action: Set Source MAC = VIRTUAL_MAC, Set Source IP = VIRTUAL_IP, Output -> CLIENT_SWITCH_PORT
        """
        # 1. Forward Path (Client -> Backend)
        if protocol == inet.IPPROTO_TCP:
            fwd_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ip_proto=inet.IPPROTO_TCP,
                ipv4_src=client_ip,
                ipv4_dst=CONFIG.VIRTUAL_IP,
                tcp_src=client_port,
            )
        elif protocol == inet.IPPROTO_UDP:
            fwd_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ip_proto=inet.IPPROTO_UDP,
                ipv4_src=client_ip,
                ipv4_dst=CONFIG.VIRTUAL_IP,
                udp_src=client_port,
            )
        else:
            fwd_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ipv4_src=client_ip,
                ipv4_dst=CONFIG.VIRTUAL_IP,
            )

        fwd_actions = [
            self.parser.OFPActionSetField(eth_dst=server.mac),
            self.parser.OFPActionSetField(ipv4_dst=server.ip),
            self.parser.OFPActionOutput(server.switch_port),
        ]

        self.add_flow(
            match=fwd_match,
            actions=fwd_actions,
            priority=CONFIG.PRIORITY_HIGH,
            idle_timeout=0,
            hard_timeout=0,
        )

        # 2. Reverse Path (Backend -> Client)
        # Fix: Remove tcp_dst/udp_dst matching so the reverse rule applies to ALL 
        # traffic from the server back to the client. We also set idle_timeout=0 
        # so this rule is permanent and prevents race conditions with L2 learning flows.
        if protocol == inet.IPPROTO_TCP:
            rev_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ip_proto=inet.IPPROTO_TCP,
                ipv4_src=server.ip,
                ipv4_dst=client_ip,
            )
        elif protocol == inet.IPPROTO_UDP:
            rev_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ip_proto=inet.IPPROTO_UDP,
                ipv4_src=server.ip,
                ipv4_dst=client_ip,
            )
        else:
            rev_match = self.parser.OFPMatch(
                eth_type=ether.ETH_TYPE_IP,
                ipv4_src=server.ip,
                ipv4_dst=client_ip,
            )

        rev_actions = [
            self.parser.OFPActionSetField(eth_src=CONFIG.VIRTUAL_MAC),
            self.parser.OFPActionSetField(ipv4_src=CONFIG.VIRTUAL_IP),
            self.parser.OFPActionOutput(CONFIG.CLIENT_SWITCH_PORT),
        ]

        self.add_flow(
            match=rev_match,
            actions=rev_actions,
            priority=CONFIG.PRIORITY_HIGH,
            idle_timeout=0,  # Permanent to avoid race conditions with L2 learning
            hard_timeout=0,  # Permanent to avoid race conditions with L2 learning
        )

        logger.info(
            f"Installed bidirectional LB flows for {client_ip}:{client_port} <-> {server.id} ({server.ip})"
        )
