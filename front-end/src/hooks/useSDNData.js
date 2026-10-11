import { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchControllerStatus,
  fetchAlgorithms,
  switchAlgorithm as apiSwitchAlgorithm,
  fetchServers,
  fetchTelemetry,
  updateServerHealth as apiUpdateServerHealth,
  connectWebSocket,
} from '../services/api';

const INITIAL_SERVERS = [
  { id: 'server1', ip: '10.0.0.2', port: 80, switch_port: 2, weight: 1, status: 'HEALTHY' },
  { id: 'server2', ip: '10.0.0.3', port: 80, switch_port: 3, weight: 2, status: 'HEALTHY' },
  { id: 'server3', ip: '10.0.0.4', port: 80, switch_port: 4, weight: 3, status: 'HEALTHY' },
];

const ALGORITHM_LIST = [
  { id: 'round_robin', name: 'Round Robin', description: 'Sequential round-robin distribution across available servers.' },
  { id: 'weighted_round_robin', name: 'Weighted Round Robin', description: 'Proportional distribution based on server capacity weights.' },
  { id: 'least_connections', name: 'Least Connections', description: 'Routes new requests to the server with fewest active TCP connections.' },
  { id: 'least_bandwidth', name: 'Least Bandwidth', description: 'Routes traffic to the server with lowest current bandwidth utilization.' },
  { id: 'random', name: 'Random', description: 'Uniformly random distribution across online server instances.' },
  { id: 'adaptive', name: 'Adaptive (AI/Feedback)', description: 'Dynamic score-based adaptation utilizing live health, response latency, and load metrics.' },
];

export function useSDNData() {
  const [isLiveConnected, setIsLiveConnected] = useState(false);
  const [simulationMode, setSimulationMode] = useState(true);
  const [activeAlgorithm, setActiveAlgorithm] = useState('round_robin');
  const [algorithms, setAlgorithms] = useState(ALGORITHM_LIST);
  const [servers, setServers] = useState(INITIAL_SERVERS);
  const [controllerStatus, setControllerStatus] = useState({
    controller_status: 'RUNNING',
    active_algorithm: 'round_robin',
    algorithm_description: 'Sequential round-robin distribution across available servers.',
    total_requests: 1240,
    healthy_servers_count: 3,
    total_servers_count: 3,
    virtual_ip: '10.0.0.100',
  });

  const [metricsHistory, setMetricsHistory] = useState([]);
  const [currentMetrics, setCurrentMetrics] = useState({
    server1: { bandwidth_mbps: 1.2, packet_rate: 15, active_connections: 4, latency_ms: 1.8, packet_loss_ratio: 0 },
    server2: { bandwidth_mbps: 2.5, packet_rate: 32, active_connections: 8, latency_ms: 2.1, packet_loss_ratio: 0 },
    server3: { bandwidth_mbps: 3.8, packet_rate: 45, active_connections: 12, latency_ms: 1.5, packet_loss_ratio: 0 },
  });

  const [trafficRate, setTrafficRate] = useState(15); // requests per second simulation
  const [trafficLogs, setTrafficLogs] = useState([]);
  const [flowRules, setFlowRules] = useState([]);
  const [lastSelectedServer, setLastSelectedServer] = useState('server1');
  const rrIndexRef = useRef(0);

  // Helper to add log entries
  const addLog = useCallback((msg, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setTrafficLogs((prev) => [
      { id: Math.random().toString(36).substring(2, 9), timestamp, msg, type },
      ...prev.slice(0, 49),
    ]);
  }, []);

  // Update flow rules display based on active algorithm and server states
  useEffect(() => {
    const healthy = servers.filter((s) => s.status === 'HEALTHY');
    const rules = [
      {
        table: 0,
        priority: 100,
        match: 'in_port=1, eth_type=0x0800, ipv4_dst=10.0.0.100',
        actions: `LOAD_BALANCER(${activeAlgorithm.toUpperCase()}) -> rewrite_dst_ip, output(port_var)`,
        description: `Virtual IP mapping to Healthy Pool [${healthy.map((h) => h.id).join(', ')}]`,
      },
      ...servers.map((s) => ({
        table: 0,
        priority: 100,
        match: `in_port=${s.switch_port}, eth_type=0x0800, ipv4_src=${s.ip}`,
        actions: `set_field:10.0.0.100->ipv4_src, set_field:00:00:00:00:00:FE->eth_src, output:1`,
        description: `Reverse NAT: Map ${s.id} (${s.ip}) response back to Virtual IP 10.0.0.100`,
      })),
      {
        table: 0,
        priority: 0,
        match: 'ALL',
        actions: 'CONTROLLER:65535 (PacketIn)',
        description: 'Table Miss: Forward unhandled ARP / discovery frames to Ryu Controller',
      },
    ];
    setFlowRules(rules);
  }, [activeAlgorithm, servers]);

  // Attempt real API polling & WebSocket connection
  useEffect(() => {
    let ws = null;
    let isCancelled = false;

    const checkBackend = async () => {
      try {
        const status = await fetchControllerStatus();
        if (!isCancelled) {
          setControllerStatus(status);
          setActiveAlgorithm(status.active_algorithm || 'round_robin');
          setIsLiveConnected(true);
          setSimulationMode(false);
          addLog('Connected to Live SDN FastAPI Backend', 'success');
        }

        const algos = await fetchAlgorithms();
        if (!isCancelled && algos && algos.length > 0) setAlgorithms(algos);

        const srvs = await fetchServers();
        if (!isCancelled && srvs && srvs.length > 0) {
          setServers(srvs.map((s) => ({ ...s, id: s.id || s.server_id })));
        }
      } catch (err) {
        if (!isCancelled) {
          setIsLiveConnected(false);
          setSimulationMode(true);
        }
      }
    };

    checkBackend();

    ws = connectWebSocket(
      (eventData) => {
        if (eventData.event_type === 'SERVER_HEALTH_CHANGED') {
          setServers((prev) =>
            prev.map((s) =>
              s.id === eventData.data.server_id ? { ...s, status: eventData.data.new_state } : s
            )
          );
          addLog(`Server ${eventData.data.server_id} state changed to ${eventData.data.new_state} (${eventData.data.reason})`, 'warning');
        } else if (eventData.event_type === 'ALGORITHM_CHANGED') {
          setActiveAlgorithm(eventData.data.new_algorithm);
          addLog(`Algorithm updated via controller to ${eventData.data.new_algorithm}`, 'info');
        } else if (eventData.event_type === 'SERVER_SELECTED') {
          setLastSelectedServer(eventData.data.selected_server);
          addLog(eventData.summary, 'success');
        }
      },
      () => setIsLiveConnected(false),
      () => setIsLiveConnected(false)
    );

    return () => {
      isCancelled = true;
      if (ws) ws.close();
    };
  }, [addLog]);

  // Live Telemetry Polling
  useEffect(() => {
    if (simulationMode || !isLiveConnected) return;

    const interval = setInterval(async () => {
      try {
        const metrics = await fetchTelemetry();
        setCurrentMetrics(metrics);

        const timeLabel = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
        setMetricsHistory((prev) => [
          ...prev.slice(-19),
          {
            time: timeLabel,
            server1_bw: metrics.server1?.bandwidth_mbps || 0,
            server2_bw: metrics.server2?.bandwidth_mbps || 0,
            server3_bw: metrics.server3?.bandwidth_mbps || 0,
            server1_conns: metrics.server1?.active_connections || 0,
            server2_conns: metrics.server2?.active_connections || 0,
            server3_conns: metrics.server3?.active_connections || 0,
          },
        ]);
      } catch (err) {
        console.error("Failed to fetch live telemetry:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [simulationMode, isLiveConnected]);

  // Simulation telemetry loop when in simulation mode
  useEffect(() => {
    if (!simulationMode) return;

    const interval = setInterval(() => {
      const healthyServers = servers.filter((s) => s.status === 'HEALTHY');
      if (healthyServers.length === 0) return;

      // Pick target server according to active algorithm logic for animation / metric distribution
      let chosenServer = healthyServers[0];

      if (activeAlgorithm === 'round_robin') {
        chosenServer = healthyServers[rrIndexRef.current % healthyServers.length];
        rrIndexRef.current += 1;
      } else if (activeAlgorithm === 'weighted_round_robin') {
        const totalWeight = healthyServers.reduce((acc, s) => acc + (s.weight || 1), 0);
        let rand = Math.random() * totalWeight;
        for (const s of healthyServers) {
          rand -= s.weight || 1;
          if (rand <= 0) {
            chosenServer = s;
            break;
          }
        }
      } else if (activeAlgorithm === 'least_connections') {
        chosenServer = [...healthyServers].sort(
          (a, b) => (currentMetrics[a.id]?.active_connections || 0) - (currentMetrics[b.id]?.active_connections || 0)
        )[0];
      } else if (activeAlgorithm === 'least_bandwidth') {
        chosenServer = [...healthyServers].sort(
          (a, b) => (currentMetrics[a.id]?.bandwidth_mbps || 0) - (currentMetrics[b.id]?.bandwidth_mbps || 0)
        )[0];
      } else if (activeAlgorithm === 'random') {
        chosenServer = healthyServers[Math.floor(Math.random() * healthyServers.length)];
      } else if (activeAlgorithm === 'adaptive') {
        // Weighted composite score based on low latency and low active connections
        chosenServer = [...healthyServers].sort((a, b) => {
          const scoreA = (currentMetrics[a.id]?.latency_ms || 2) * 0.5 + (currentMetrics[a.id]?.active_connections || 0) * 0.5;
          const scoreB = (currentMetrics[b.id]?.latency_ms || 2) * 0.5 + (currentMetrics[b.id]?.active_connections || 0) * 0.5;
          return scoreA - scoreB;
        })[0];
      }

      setLastSelectedServer(chosenServer.id);

      // Generate randomized realistic variance
      const timeLabel = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
      const newMetrics = {};

      servers.forEach((srv) => {
        if (srv.status !== 'HEALTHY') {
          newMetrics[srv.id] = {
            server_id: srv.id,
            switch_port: srv.switch_port,
            bandwidth_mbps: 0.0,
            packet_rate: 0,
            active_connections: 0,
            latency_ms: 0,
            packet_loss_ratio: 1.0,
          };
          return;
        }

        const isChosen = srv.id === chosenServer.id;
        const baseConns = isChosen ? Math.floor(trafficRate * 0.6 + Math.random() * 5) : Math.max(1, Math.floor(Math.random() * 4));
        const baseBw = isChosen ? Number((trafficRate * 0.25 + Math.random() * 1.5).toFixed(2)) : Number((0.5 + Math.random() * 0.5).toFixed(2));
        const basePkt = isChosen ? Math.floor(trafficRate * 3 + Math.random() * 10) : Math.floor(Math.random() * 5);
        const latency = Number((1.2 + Math.random() * 1.4).toFixed(2));

        newMetrics[srv.id] = {
          server_id: srv.id,
          switch_port: srv.switch_port,
          bandwidth_mbps: baseBw,
          packet_rate: basePkt,
          active_connections: baseConns,
          latency_ms: latency,
          packet_loss_ratio: 0.0,
        };
      });

      setCurrentMetrics(newMetrics);

      // Append to history for real-time charting (keep last 20 ticks)
      setMetricsHistory((prev) => [
        ...prev.slice(-19),
        {
          time: timeLabel,
          server1_bw: newMetrics.server1?.bandwidth_mbps || 0,
          server2_bw: newMetrics.server2?.bandwidth_mbps || 0,
          server3_bw: newMetrics.server3?.bandwidth_mbps || 0,
          server1_conns: newMetrics.server1?.active_connections || 0,
          server2_conns: newMetrics.server2?.active_connections || 0,
          server3_conns: newMetrics.server3?.active_connections || 0,
        },
      ]);

      setControllerStatus((prev) => ({
        ...prev,
        total_requests: prev.total_requests + Math.max(1, Math.floor(trafficRate / 2)),
        healthy_servers_count: healthyServers.length,
      }));
    }, 1500);

    return () => clearInterval(interval);
  }, [simulationMode, activeAlgorithm, servers, trafficRate, currentMetrics]);

  // Handler to switch algorithm
  const switchAlgoHandler = async (algoId) => {
    setActiveAlgorithm(algoId);
    const selectedAlgo = algorithms.find((a) => a.id === algoId);
    setControllerStatus((prev) => ({
      ...prev,
      active_algorithm: algoId,
      algorithm_description: selectedAlgo?.description || '',
    }));
    addLog(`Switched algorithm to ${selectedAlgo?.name || algoId}`, 'info');

    if (!simulationMode) {
      try {
        await apiSwitchAlgorithm(algoId);
      } catch (err) {
        addLog(`Backend algorithm switch error: ${err.message}`, 'error');
      }
    }
  };

  // Handler to update server health
  const toggleServerHealth = async (serverId, newStatus) => {
    setServers((prev) =>
      prev.map((s) => (s.id === serverId ? { ...s, status: newStatus } : s))
    );
    addLog(`Server ${serverId} health state set to ${newStatus}`, newStatus === 'HEALTHY' ? 'success' : 'warning');

    if (!simulationMode) {
      try {
        await apiUpdateServerHealth(serverId, newStatus);
      } catch (err) {
        addLog(`Backend health update error: ${err.message}`, 'error');
      }
    }
  };

  // Handler to update server weight
  const updateServerWeight = (serverId, weight) => {
    setServers((prev) =>
      prev.map((s) => (s.id === serverId ? { ...s, weight: Math.max(1, parseInt(weight, 10) || 1) } : s))
    );
    addLog(`Updated ${serverId} weight capacity to ${weight}`, 'info');
  };

  // Send single manual test packet request from client
  const triggerSingleRequest = () => {
    const healthyServers = servers.filter((s) => s.status === 'HEALTHY');
    if (healthyServers.length === 0) {
      addLog('HTTP Request Failed: 503 Service Unavailable (All backend servers down)', 'error');
      return;
    }
    const target = healthyServers[Math.floor(Math.random() * healthyServers.length)];
    addLog(`HTTP GET http://10.0.0.100:80 -> Routed to ${target.id} (${target.ip}:80) via Switch Port ${target.switch_port}`, 'success');
  };

  return {
    isLiveConnected,
    simulationMode,
    setSimulationMode,
    activeAlgorithm,
    algorithms,
    servers,
    controllerStatus,
    currentMetrics,
    metricsHistory,
    trafficRate,
    setTrafficRate,
    trafficLogs,
    flowRules,
    lastSelectedServer,
    switchAlgorithm: switchAlgoHandler,
    toggleServerHealth,
    updateServerWeight,
    triggerSingleRequest,
    addLog,
  };
}
