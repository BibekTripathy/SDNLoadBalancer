import { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchControllerStatus,
  fetchAlgorithms,
  switchAlgorithm as apiSwitchAlgorithm,
  fetchServers,
  fetchTelemetry,
  updateServerHealth as apiUpdateServerHealth,
  addServer as apiAddServer,
  removeServer as apiRemoveServer,
  drainServer as apiDrainServer,
  updateServerWeight as apiUpdateServerWeight,
  triggerClientRequest,
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

export function selectServerByAlgorithm(algo, healthyServers, currentMetrics, rrIndexRef) {
  if (!healthyServers || healthyServers.length === 0) return null;
  if (healthyServers.length === 1) return healthyServers[0];

  if (algo === 'round_robin') {
    const idx = (rrIndexRef.current || 0) % healthyServers.length;
    rrIndexRef.current = idx + 1;
    return healthyServers[idx];
  }

  if (algo === 'weighted_round_robin') {
    const totalWeight = healthyServers.reduce((acc, s) => acc + (s.weight || 1), 0);
    let rand = Math.random() * totalWeight;
    for (const s of healthyServers) {
      rand -= s.weight || 1;
      if (rand <= 0) return s;
    }
    return healthyServers[0];
  }

  if (algo === 'least_connections') {
    return [...healthyServers].sort(
      (a, b) =>
        (currentMetrics[a.id || a.server_id]?.active_connections || 0) -
        (currentMetrics[b.id || b.server_id]?.active_connections || 0)
    )[0];
  }

  if (algo === 'least_bandwidth') {
    return [...healthyServers].sort(
      (a, b) =>
        (currentMetrics[a.id || a.server_id]?.bandwidth_mbps || 0) -
        (currentMetrics[b.id || b.server_id]?.bandwidth_mbps || 0)
    )[0];
  }

  if (algo === 'adaptive') {
    return [...healthyServers].sort((a, b) => {
      const aId = a.id || a.server_id;
      const bId = b.id || b.server_id;
      const scoreA =
        (currentMetrics[aId]?.latency_ms || 2) * 0.5 +
        (currentMetrics[aId]?.active_connections || 0) * 0.5;
      const scoreB =
        (currentMetrics[bId]?.latency_ms || 2) * 0.5 +
        (currentMetrics[bId]?.active_connections || 0) * 0.5;
      return scoreA - scoreB;
    })[0];
  }

  // Fallback / 'random'
  return healthyServers[Math.floor(Math.random() * healthyServers.length)];
}

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
        description: `Virtual IP mapping to Healthy Pool [${healthy.map((h) => h.id || h.server_id).join(', ')}]`,
      },
      ...servers.map((s) => ({
        table: 0,
        priority: 100,
        match: `in_port=${s.switch_port}, eth_type=0x0800, ipv4_src=${s.ip}`,
        actions: `set_field:10.0.0.100->ipv4_src, set_field:00:00:00:00:00:FE->eth_src, output:1`,
        description: `Reverse NAT: Map ${s.id || s.server_id} (${s.ip}) response back to Virtual IP 10.0.0.100`,
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
          const srvId = eventData.data.server_id;
          setServers((prev) =>
            prev.map((s) =>
              (s.id || s.server_id) === srvId ? { ...s, status: eventData.data.new_state } : s
            )
          );
          addLog(`Server ${srvId} state changed to ${eventData.data.new_state} (${eventData.data.reason})`, 'warning');
        } else if (eventData.event_type === 'SERVER_ADDED') {
          const newSrv = eventData.data;
          const srvId = newSrv.server_id || newSrv.id;
          setServers((prev) => {
            if (prev.some((s) => (s.id || s.server_id) === srvId)) return prev;
            return [...prev, { ...newSrv, id: srvId }];
          });
          addLog(eventData.summary || `Backend server ${srvId} added to pool`, 'success');
        } else if (eventData.event_type === 'SERVER_REMOVED') {
          const removedId = eventData.data.server_id;
          setServers((prev) => prev.filter((s) => (s.id || s.server_id) !== removedId));
          setCurrentMetrics((prev) => {
            const copy = { ...prev };
            delete copy[removedId];
            return copy;
          });
          addLog(eventData.summary || `Backend server ${removedId} removed from pool`, 'warning');
        } else if (eventData.event_type === 'SERVER_DRAINING') {
          const srvId = eventData.data.server_id;
          setServers((prev) =>
            prev.map((s) => ((s.id || s.server_id) === srvId ? { ...s, status: 'DRAINING' } : s))
          );
          addLog(eventData.summary || `Backend server ${srvId} marked as DRAINING`, 'warning');
        } else if (eventData.event_type === 'SERVER_WEIGHT_UPDATED') {
          const { server_id, weight } = eventData.data;
          setServers((prev) =>
            prev.map((s) => ((s.id || s.server_id) === server_id ? { ...s, weight } : s))
          );
          addLog(eventData.summary || `Server ${server_id} weight capacity set to ${weight}`, 'info');
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

  // Live Telemetry Polling: poll real metrics if Mininet is running
  useEffect(() => {
    if (!isLiveConnected) return;

    const interval = setInterval(async () => {
      try {
        const metrics = await fetchTelemetry();
        // Check if real Mininet switch traffic is actively flowing
        const hasRealTraffic = Object.values(metrics).some(
          (m) => (m.bandwidth_mbps || 0) > 0 || (m.packet_rate || 0) > 0 || (m.rx_packets || 0) > 100
        );

        if (hasRealTraffic) {
          // Real Mininet traffic detected: apply real switch metrics!
          setCurrentMetrics(metrics);
          const timeLabel = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
          const historyItem = { time: timeLabel };
          servers.forEach((s) => {
            const srvId = s.id || s.server_id;
            historyItem[`${srvId}_bw`] = metrics[srvId]?.bandwidth_mbps || 0;
            historyItem[`${srvId}_conns`] = metrics[srvId]?.active_connections || 0;
          });
          setMetricsHistory((prev) => [...prev.slice(-19), historyItem]);
        }
      } catch (err) {
        console.error('Failed to fetch live telemetry:', err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [isLiveConnected, servers]);

  // Dynamic Traffic & Metric Generator Loop
  useEffect(() => {
    if (trafficRate <= 0) {
      // Idle ticker to keep time moving on the telemetry charts even when traffic rate is 0
      const idleInterval = setInterval(() => {
        const timeLabel = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });
        const historyItem = { time: timeLabel };
        servers.forEach((s) => {
          const srvId = s.id || s.server_id;
          historyItem[`${srvId}_bw`] = currentMetrics[srvId]?.bandwidth_mbps || 0;
          historyItem[`${srvId}_conns`] = currentMetrics[srvId]?.active_connections || 0;
        });
        setMetricsHistory((prev) => [...prev.slice(-19), historyItem]);
      }, 2000);
      return () => clearInterval(idleInterval);
    }

    const interval = setInterval(() => {
      const healthyServers = servers.filter((s) => s.status === 'HEALTHY');
      const timeLabel = new Date().toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' });

      if (healthyServers.length === 0) {
        // All servers are down or draining
        const zeroMetrics = {};
        servers.forEach((srv) => {
          const srvId = srv.id || srv.server_id;
          zeroMetrics[srvId] = {
            server_id: srvId,
            switch_port: srv.switch_port,
            bandwidth_mbps: 0.0,
            packet_rate: 0,
            active_connections: 0,
            latency_ms: 0,
            packet_loss_ratio: 1.0,
          };
        });
        setCurrentMetrics(zeroMetrics);
        return;
      }

      // Pick target server according to active algorithm logic
      const chosenServer = selectServerByAlgorithm(activeAlgorithm, healthyServers, currentMetrics, rrIndexRef);
      if (!chosenServer) return;
      const chosenId = chosenServer.id || chosenServer.server_id;

      // Update selected server so packet animation routes to it
      setLastSelectedServer(chosenId);

      // Generate realistic variance per server proportional to trafficRate
      const newMetrics = {};
      servers.forEach((srv) => {
        const srvId = srv.id || srv.server_id;
        if (srv.status !== 'HEALTHY') {
          newMetrics[srvId] = {
            server_id: srvId,
            switch_port: srv.switch_port,
            bandwidth_mbps: 0.0,
            packet_rate: 0,
            active_connections: 0,
            latency_ms: 0,
            packet_loss_ratio: 1.0,
          };
          return;
        }

        const isChosen = srvId === chosenId;
        const baseConns = isChosen
          ? Math.floor(trafficRate * 0.4 + Math.random() * 4 + 1)
          : Math.max(1, Math.floor(Math.random() * 3));
        const baseBw = isChosen
          ? Number((trafficRate * 0.18 + Math.random() * 1.2).toFixed(2))
          : Number((0.3 + Math.random() * 0.4).toFixed(2));
        const basePkt = isChosen
          ? Math.floor(trafficRate * 2.5 + Math.random() * 8)
          : Math.floor(Math.random() * 4);
        const latency = Number((1.2 + Math.random() * 1.4).toFixed(2));

        newMetrics[srvId] = {
          server_id: srvId,
          switch_port: srv.switch_port,
          bandwidth_mbps: baseBw,
          packet_rate: basePkt,
          active_connections: baseConns,
          latency_ms: latency,
          packet_loss_ratio: 0.0,
        };
      });

      setCurrentMetrics(newMetrics);

      // Append to history for real-time charting
      const historyItem = { time: timeLabel };
      servers.forEach((s) => {
        const srvId = s.id || s.server_id;
        historyItem[`${srvId}_bw`] = newMetrics[srvId]?.bandwidth_mbps || 0;
        historyItem[`${srvId}_conns`] = newMetrics[srvId]?.active_connections || 0;
      });

      setMetricsHistory((prev) => [...prev.slice(-19), historyItem]);

      setControllerStatus((prev) => ({
        ...prev,
        total_requests: (prev.total_requests || 0) + Math.max(1, Math.floor(trafficRate / 2)),
        healthy_servers_count: healthyServers.length,
        total_servers_count: servers.length,
      }));
    }, 1500);

    return () => clearInterval(interval);
  }, [trafficRate, activeAlgorithm, servers, currentMetrics]);

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
      prev.map((s) => ((s.id || s.server_id) === serverId ? { ...s, status: newStatus } : s))
    );
    addLog(
      `Server ${serverId} health state set to ${newStatus}`,
      newStatus === 'HEALTHY' ? 'success' : 'warning'
    );

    if (!simulationMode) {
      try {
        await apiUpdateServerHealth(serverId, newStatus);
      } catch (err) {
        addLog(`Backend health update error: ${err.message}`, 'error');
      }
    }
  };

  // Handler to add a server
  const addServerHandler = async (serverData) => {
    const cleanId = serverData.id || serverData.server_id;
    const cleanData = {
      ...serverData,
      id: cleanId,
      server_id: cleanId,
    };

    if (!simulationMode) {
      try {
        const result = await apiAddServer(cleanData);
        setServers((prev) => {
          if (prev.some((s) => (s.id || s.server_id) === cleanId)) return prev;
          return [...prev, { ...cleanData, status: result.status || 'HEALTHY' }];
        });
        addLog(`[Live Mode] Backend ${cleanId} deployed and registered`, 'success');
        return result;
      } catch (err) {
        addLog(`Backend deployment error: ${err.message}`, 'error');
        throw err;
      }
    } else {
      setServers((prev) => [...prev, cleanData]);
      setCurrentMetrics((prev) => ({
        ...prev,
        [cleanId]: {
          bandwidth_mbps: 0.0,
          packet_rate: 0,
          active_connections: 0,
          latency_ms: 1.5,
          packet_loss_ratio: 0.0,
        },
      }));
      addLog(`[Simulation] Backend server ${cleanId} added to pool`, 'success');
      return cleanData;
    }
  };

  // Handler to remove a server
  const removeServerHandler = async (serverId) => {
    if (!simulationMode) {
      try {
        await apiRemoveServer(serverId);
        setServers((prev) => prev.filter((s) => (s.id || s.server_id) !== serverId));
        setCurrentMetrics((prev) => {
          const copy = { ...prev };
          delete copy[serverId];
          return copy;
        });
        addLog(`[Live Mode] Backend ${serverId} removed and OpenFlow rules cleaned`, 'warning');
      } catch (err) {
        addLog(`Backend removal error: ${err.message}`, 'error');
        throw err;
      }
    } else {
      setServers((prev) => prev.filter((s) => (s.id || s.server_id) !== serverId));
      setCurrentMetrics((prev) => {
        const copy = { ...prev };
        delete copy[serverId];
        return copy;
      });
      addLog(`[Simulation] Backend ${serverId} removed from pool`, 'warning');
    }
  };

  // Handler to drain server
  const drainServerHandler = async (serverId) => {
    setServers((prev) =>
      prev.map((s) => ((s.id || s.server_id) === serverId ? { ...s, status: 'DRAINING' } : s))
    );
    addLog(`Server ${serverId} marked as DRAINING (rejecting new selections)`, 'warning');

    if (!simulationMode) {
      try {
        await apiDrainServer(serverId);
      } catch (err) {
        addLog(`Backend drain error: ${err.message}`, 'error');
      }
    }
  };

  // Handler to update server weight
  const updateWeightHandler = async (serverId, weight) => {
    const numWeight = Math.max(1, parseInt(weight, 10) || 1);
    setServers((prev) =>
      prev.map((s) => ((s.id || s.server_id) === serverId ? { ...s, weight: numWeight } : s))
    );
    addLog(`Updated ${serverId} weight capacity to ${numWeight}`, 'info');

    if (!simulationMode) {
      try {
        await apiUpdateServerWeight(serverId, numWeight);
      } catch (err) {
        addLog(`Backend weight update error: ${err.message}`, 'error');
      }
    }
  };

  // Send single manual test packet request from client
  const triggerSingleRequest = async () => {
    const healthyServers = servers.filter((s) => s.status === 'HEALTHY');
    if (healthyServers.length === 0) {
      addLog('HTTP Request Failed: 503 Service Unavailable (All backend servers down)', 'error');
      return;
    }

    const target = selectServerByAlgorithm(activeAlgorithm, healthyServers, currentMetrics, rrIndexRef);
    if (!target) return;
    const targetId = target.id || target.server_id;

    // Immediately update selected server so visualizer animations and packet spawner see it
    setLastSelectedServer(targetId);

    // Increment request count in controller status
    setControllerStatus((prev) => ({
      ...prev,
      total_requests: (prev.total_requests || 0) + 1,
    }));

    addLog(
      `HTTP GET http://10.0.0.100:80 -> Routed to ${targetId} (${target.ip}:80) via Switch Port ${target.switch_port} [${activeAlgorithm.toUpperCase()}]`,
      'success'
    );

    // Update telemetry for this server so connections and latency reflect the request
    setCurrentMetrics((prev) => {
      const cur = prev[targetId] || { active_connections: 0, bandwidth_mbps: 0, packet_rate: 0, latency_ms: 1.5 };
      return {
        ...prev,
        [targetId]: {
          ...cur,
          server_id: targetId,
          switch_port: target.switch_port,
          active_connections: (cur.active_connections || 0) + 1,
          bandwidth_mbps: Number(((cur.bandwidth_mbps || 0) + 0.4).toFixed(2)),
          packet_rate: (cur.packet_rate || 0) + 4,
          latency_ms: Number((1.2 + Math.random() * 1.5).toFixed(2)),
        },
      };
    });

    // If live API connected, also send trigger to backend controller
    if (isLiveConnected) {
      try {
        const res = await triggerClientRequest();
        if (res && res.selected_server) {
          setLastSelectedServer(res.selected_server);
        }
      } catch (e) {
        // Local simulation handled above
      }
    }
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
    addServer: addServerHandler,
    removeServer: removeServerHandler,
    drainServer: drainServerHandler,
    updateServerWeight: updateWeightHandler,
    triggerSingleRequest,
    addLog,
  };
}

