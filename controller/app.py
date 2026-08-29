"""
Main Ryu SDN Controller Application for Dynamic Load Balancing.
"""

import logging
from typing import Any, Dict, Optional

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ethernet, ether_types, in_proto, ipv4, packet, tcp, udp
from ryu.ofproto import ofproto_v1_3

from controller.config import CONFIG
from controller.events import ControllerEvent, EventType
from controller.flow_manager import FlowManager
from controller.health_monitor import HealthMonitor
from controller.load_balancer import LoadBalancerEngine
from controller.telemetry import TelemetryCollector

logger = logging.getLogger(__name__)


class SDNLoadBalancerApp(app_manager.RyuApp):
    """Ryu Controller application managing OpenFlow 1.3 switch and dynamic load balancing."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SDNLoadBalancerApp, self).__init__(*args, **kwargs)
        self.name = "sdn_load_balancer"
        self.datapaths: Dict[int, Any] = {}
        self.flow_managers: Dict[int, FlowManager] = {}

        # Initialize Subsystems
        self.telemetry = TelemetryCollector(CONFIG.SERVERS)
        self.health_monitor = HealthMonitor(
            CONFIG.SERVERS, event_callback=self.on_controller_event
        )
        self.load_balancer = LoadBalancerEngine(
            telemetry=self.telemetry,
            health_monitor=self.health_monitor,
            default_algorithm="round_robin",
            event_callback=self.on_controller_event,
        )

        # Global event listeners (for WebSocket / REST bridge)
        self.event_listeners = []

        # Start background telemetry polling thread
        self.monitor_thread = hub.spawn(self._telemetry_monitor_loop)
        logger.info("SDN Dynamic Load Balancer App initialized.")

    def add_event_listener(self, listener_fn):
        """Registers a callback to receive real-time controller events."""
        self.event_listeners.append(listener_fn)

    def on_controller_event(self, event: ControllerEvent):
        """Dispatches controller events to registered listeners."""
        for listener in self.event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error notifying event listener: {e}")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handles switch connection and installs base table-miss flow rule."""
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        flow_mgr = FlowManager(datapath)
        self.flow_managers[dpid] = flow_mgr

        # Install table-miss flow entry
        flow_mgr.install_table_miss_flow()
        logger.info(f"Switch dpid={dpid} connected and configured.")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Processes incoming packets sent from switch to controller."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth:
            return

        # Ignore LLDP packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Handle ARP Requests
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self._handle_arp(datapath, in_port, pkt, eth)
            return

        # Handle IPv4 Packets
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            self._handle_ipv4(datapath, in_port, pkt, eth, msg)
            return

    def _handle_arp(self, datapath, in_port, pkt, eth):
        """Resolves ARP requests for Virtual IP and host machines."""
        arp_pkt = pkt.get_protocol(arp.arp)
        if not arp_pkt or arp_pkt.opcode != arp.ARP_REQUEST:
            return

        target_ip = arp_pkt.dst_ip
        src_ip = arp_pkt.src_ip
        src_mac = eth.src

        # Respond to ARP for Virtual IP
        if target_ip == CONFIG.VIRTUAL_IP:
            reply_mac = CONFIG.VIRTUAL_MAC
            self._send_arp_reply(datapath, in_port, target_ip, reply_mac, src_ip, src_mac)
            return

        # Respond to ARP for known Backend Servers
        for s in CONFIG.SERVERS:
            if target_ip == s.ip:
                self._send_arp_reply(datapath, in_port, target_ip, s.mac, src_ip, src_mac)
                return

        # Respond to ARP for Client
        if target_ip == CONFIG.CLIENT_IP:
            self._send_arp_reply(
                datapath, in_port, target_ip, CONFIG.CLIENT_MAC, src_ip, src_mac
            )
            return

    def _send_arp_reply(self, datapath, in_port, sender_ip, sender_mac, target_ip, target_mac):
        """Constructs and sends an ARP reply packet."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        reply_pkt = packet.Packet()
        reply_pkt.add_protocol(
            ethernet.ethernet(
                ethertype=ether_types.ETH_TYPE_ARP,
                dst=target_mac,
                src=sender_mac,
            )
        )
        reply_pkt.add_protocol(
            arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=sender_mac,
                src_ip=sender_ip,
                dst_mac=target_mac,
                dst_ip=target_ip,
            )
        )
        reply_pkt.serialize()

        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=reply_pkt.data,
        )
        datapath.send_msg(out)

    def _handle_ipv4(self, datapath, in_port, pkt, eth, msg):
        """Processes IP traffic directed to Virtual IP and selects backend server."""
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return

        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst
        proto = ip_pkt.proto

        # Only load balance traffic destined for the Virtual IP
        if dst_ip != CONFIG.VIRTUAL_IP:
            return

        src_port = 0
        dst_port = 0
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)

        if tcp_pkt:
            src_port = tcp_pkt.src_port
            dst_port = tcp_pkt.dst_port
        elif udp_pkt:
            src_port = udp_pkt.src_port
            dst_port = udp_pkt.dst_port

        client_info = {
            "client_ip": src_ip,
            "client_port": src_port,
            "dest_ip": dst_ip,
            "dest_port": dst_port,
            "protocol": "TCP" if tcp_pkt else ("UDP" if udp_pkt else "OTHER"),
        }

        # Emit Request Received Event
        self.on_controller_event(
            ControllerEvent(
                event_type=EventType.REQUEST_RECEIVED,
                data=client_info,
                summary=f"Incoming request from {src_ip}:{src_port} -> VIP {dst_ip}:{dst_port}",
            )
        )

        # Select backend server using active algorithm
        try:
            selected_server, reasoning = self.load_balancer.select_backend(client_info)
        except Exception as err:
            logger.error(f"Failed to select backend server: {err}")
            return

        # Install flow rules
        flow_mgr = self.flow_managers.get(datapath.id)
        if flow_mgr:
            flow_mgr.install_lb_flows(
                client_ip=src_ip,
                client_port=src_port,
                server=selected_server,
                protocol=proto,
            )
            self.on_controller_event(
                ControllerEvent(
                    event_type=EventType.FLOW_INSTALLED,
                    data={
                        "client_ip": src_ip,
                        "client_port": src_port,
                        "server_id": selected_server.id,
                        "server_ip": selected_server.ip,
                    },
                    summary=f"Flow installed: {src_ip}:{src_port} <-> {selected_server.id}",
                )
            )

        # Forward current packet directly out to the chosen backend server
        parser = datapath.ofproto_parser
        actions = [
            parser.OFPActionSetField(eth_dst=selected_server.mac),
            parser.OFPActionSetField(ipv4_dst=selected_server.ip),
            parser.OFPActionOutput(selected_server.switch_port),
        ]
        data = None
        if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

        self.on_controller_event(
            ControllerEvent(
                event_type=EventType.PACKET_FORWARDED,
                data={
                    "client_ip": src_ip,
                    "target_server": selected_server.id,
                    "target_port": selected_server.switch_port,
                },
                summary=f"Packet forwarded to {selected_server.id} via port {selected_server.switch_port}",
            )
        )

    def _telemetry_monitor_loop(self):
        """Periodically requests OpenFlow port statistics from connected switches."""
        while True:
            for dp in list(self.datapaths.values()):
                self._request_stats(dp)
            hub.sleep(CONFIG.STAT_INTERVAL)

    def _request_stats(self, datapath):
        """Sends OFPPortStatsRequest and OFPFlowStatsRequest to switch."""
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, datapath.ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Processes port statistics reply from switch."""
        body = ev.msg.body
        self.telemetry.update_port_stats(body)
        
        # Broadcast Telemetry Update Event
        self.on_controller_event(
            ControllerEvent(
                event_type=EventType.TELEMETRY_UPDATED,
                data=self.telemetry.get_all_metrics(),
                summary="Telemetry statistics refreshed",
            )
        )
