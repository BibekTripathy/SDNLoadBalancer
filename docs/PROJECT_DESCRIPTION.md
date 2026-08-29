# SDN Dynamic Load Balancer Project Description

TITLE: Adaptive SDN-Based Dynamic Load Balancing Using Real-Time Network Telemetry

  Build a two-person Computer Networks project using Mininet + Open vSwitch + Ryu/OpenFlow 1.3, with a professional React dashboard.

  CORE ARCHITECTURE:
  React/TypeScript/Vite frontend
          ↓ REST + WebSocket
  FastAPI backend/API gateway
          ↓
  Ryu SDN Controller
          ↓ OpenFlow 1.3
  Open vSwitch (OVS)
          ↓
  Client + 3 Backend Servers

  NETWORK:
  - Mininet topology
  - 1 client
  - 1 OVS switch initially
  - 3 backend servers
  - Virtual IP (VIP), e.g. 10.0.0.100
  - Client sends traffic only to VIP
  - Controller dynamically selects backend
  - OpenFlow rules perform forwarding and required IP/MAC rewriting
  - Use Python 3

  CONTROLLER MODULES:
  controller/
    app.py
    flow_manager.py
    telemetry.py
    health_monitor.py
    load_balancer.py
    api/
    algorithms/
      round_robin.py
      random.py
      least_connections.py
      least_bandwidth.py
      weighted_round_robin.py
      adaptive.py

  ALGORITHM DESIGN:
  Implement all algorithms behind a common interface/function so the active algorithm can be changed at runtime without restarting Mininet/Ryu.

  Algorithms:
  1. Round Robin
  2. Random
  3. Least Connections
  4. Least Bandwidth
  5. Weighted Round Robin
  6. Adaptive/Composite

  Adaptive algorithm can calculate a normalized load score using:
  - bandwidth utilization
  - active connections
  - latency
  - packet loss

  Example:
  score =
    0.4 * bandwidth +
    0.3 * connections +
    0.2 * latency +
    0.1 * packet_loss

  Select the backend with the lowest score.

  TELEMETRY:
  Ryu periodically collects OpenFlow port statistics:
  - RX/TX bytes
  - packets
  - drops
  - bandwidth/utilization
  - packet rate

  Track server metrics:
  - active connections
  - latency
  - health
  - traffic/load

  HEALTH MONITORING:
  - Periodically check backend health
  - Mark servers HEALTHY/DOWN/RECOVERING
  - Automatically remove failed servers from load-balancing pool
  - Automatically re-add recovered servers
  - Allow simulated server failure/high load for demonstrations

  FLOW/DECISION EVENTS:
  The controller should emit structured events such as:
  - REQUEST_RECEIVED
  - ALGORITHM_CHANGED
  - SERVER_SELECTED
  - FLOW_INSTALLED
  - PACKET_FORWARDED
  - SERVER_HEALTH_CHANGED

  Frontend receives these through WebSocket and visualizes them.

  FRONTEND:
  React + TypeScript + Vite
  Tailwind CSS
  React Flow for topology
  Recharts for metrics

  Main dashboard should look like a Network Operations Center.

  DASHBOARD FEATURES:
  1. Overview
     - controller status
     - server health cards
     - current algorithm
     - total requests
     - active connections
     - throughput
     - latency
     - topology

  2. Live Network Topology
     - Client → OVS → Server 1/2/3
     - visually show link utilization
     - highlight selected backend
     - animate packet/request flow from client through OVS to selected server
     - show server load on nodes
     - show HEALTHY/DOWN state

  3. Algorithm Control
     - dropdown/radio selection for all algorithms
     - Apply algorithm without restarting network
     - show currently active algorithm

  4. Algorithm Reasoning / Decision Visualization
  For every request display:
     Request received
         ↓
     algorithm selected
         ↓
     server metrics evaluated
         ↓
     selected backend
         ↓
     OpenFlow rule installed
         ↓
     traffic forwarded

  Example:
  Server 1: 32% load
  Server 2: 71% load
  Server 3: 24% load
  → Adaptive/Least Bandwidth chooses Server 3

  For Adaptive mode, show the scoring breakdown:
  - bandwidth score
  - connection score
  - latency score
  - packet loss score
  - final composite score

  5. Live Event Log
  Example:
  22:31:04 Request received
  22:31:04 Algorithm: Least Bandwidth
  22:31:04 S1: 8.2 Mbps
  22:31:04 S2: 18.7 Mbps
  22:31:04 S3: 4.1 Mbps
  22:31:04 Selected: Server 3
  22:31:04 Flow installed
  22:31:04 Request forwarded → S3

  6. Flow Table Viewer
  Allow clicking OVS and viewing current OpenFlow rules:
  - priority
  - match
  - actions
  - selected backend
  Highlight newly installed/active flows.

  7. Packet/Flow Inspector
  Click an animated request/flow and show:
  - source IP
  - destination/VIP
  - protocol
  - source/destination port
  - selected backend
  - active algorithm
  - decision reason

  8. Metrics
  Real-time charts:
  - bandwidth vs time
  - latency vs time
  - requests/sec
  - active connections
  - packet loss
  - server load
  - throughput

  9. Experiment/Benchmark page
  Compare algorithms using:
  - throughput
  - average latency
  - P95 latency
  - packet loss
  - requests/sec
  - load distribution

  Compare:
  Round Robin vs Least Connections vs Least Bandwidth vs Adaptive.

  TRAFFIC/TESTING:
  Use:
  - iperf3
  - wrk
  - curl
  - ping
  - tcpdump/Wireshark

  Provide controls for:
  - traffic generation
  - requests/sec
  - duration
  - simulated high load
  - simulated server failure

  IMPORTANT SEPARATION:
  Frontend must NOT implement routing algorithms.
  Ryu is the source of truth.

  Flow:
  React
   → FastAPI
   → Ryu
   → algorithm evaluates telemetry
   → Ryu selects backend
   → Ryu installs OpenFlow rule on OVS
   → Ryu emits event
   → FastAPI/WebSocket
   → React updates topology, packet animation, metrics and reasoning.

  PROJECT DEVELOPMENT PHASES:

  Phase 1:
  Mininet + OVS + Ryu
  Verify OpenFlow connectivity and pingall.

  Phase 2:
  Client + VIP + 3 servers.
  Implement basic forwarding/NAT and Round Robin.

  Phase 3:
  Implement all algorithms behind common interface.

  Phase 4:
  Add OpenFlow telemetry and dynamic load calculation.

  Phase 5:
  Add server health/failure detection and recovery.

  Phase 6:
  FastAPI + WebSocket event API.

  Phase 7:
  React dashboard + live topology + packet animations.

  Phase 8:
  Benchmark algorithms and generate graphs/results.

  Phase 9:
  Polish UI, documentation, architecture diagrams, demo mode.

  IMPORTANT IMPLEMENTATION PRINCIPLES:
  - Start simple and keep every phase independently testable.
  - Do not over-engineer initially.
  - Use OpenFlow 1.3 consistently.
  - Keep controller, API, frontend, and networking code modular.
  - Use real controller/network data in the final dashboard; mock data only for initial UI development.
  - The dashboard should visualize logical packet/flow events rather than attempting to render every physical packet.
  - Validate actual forwarding with tcpdump/Wireshark.
  - The final demo should clearly show:
    1. topology
    2. algorithm selection
    3. live packet/flow visualization
    4. controller reasoning
    5. dynamic load redistribution
    6. server failure/recovery
    7. algorithm performance comparison.

  FINAL GOAL:
  Create a polished SDN Network Operations Center where a professor can visually see the Ryu controller receive telemetry, evaluate the selected load-balancing algorithm,
  choose a backend server, install OpenFlow rules, and dynamically redirect traffic as server/network conditions change.