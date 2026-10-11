/**
 * SDN Load Balancer API Service
 * Handles REST endpoints and WebSocket real-time event streams.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/ws/events';

export const fetchControllerStatus = async () => {
  const response = await fetch(`${API_BASE_URL}/api/controller/status`);
  if (!response.ok) throw new Error('Failed to fetch controller status');
  return response.json();
};

export const fetchAlgorithms = async () => {
  const response = await fetch(`${API_BASE_URL}/api/controller/algorithms`);
  if (!response.ok) throw new Error('Failed to fetch load balancing algorithms');
  return response.json();
};

export const switchAlgorithm = async (algorithmId) => {
  const response = await fetch(`${API_BASE_URL}/api/controller/algorithm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ algorithm: algorithmId }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to switch algorithm');
  }
  return response.json();
};

export const triggerClientRequest = async () => {
  const response = await fetch(`${API_BASE_URL}/api/controller/request`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to trigger request');
  }
  return response.json();
};

export const fetchServers = async () => {
  const response = await fetch(`${API_BASE_URL}/api/servers`);
  if (!response.ok) {
    // Fallback to legacy endpoint if needed
    const fallback = await fetch(`${API_BASE_URL}/api/controller/servers`);
    if (!fallback.ok) throw new Error('Failed to fetch server pool');
    return fallback.json();
  }
  return response.json();
};

export const fetchServerSuggest = async () => {
  const response = await fetch(`${API_BASE_URL}/api/servers/suggest`);
  if (!response.ok) throw new Error('Failed to fetch server suggestion');
  return response.json();
};

export const addServer = async (serverData) => {
  const response = await fetch(`${API_BASE_URL}/api/servers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serverData),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to add backend server');
  }
  return response.json();
};

export const removeServer = async (serverId) => {
  const response = await fetch(`${API_BASE_URL}/api/servers/${serverId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to remove backend server');
  }
  return response.json();
};

export const drainServer = async (serverId) => {
  const response = await fetch(`${API_BASE_URL}/api/servers/${serverId}/drain`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to drain backend server');
  }
  return response.json();
};

export const updateServerWeight = async (serverId, weight) => {
  const response = await fetch(`${API_BASE_URL}/api/servers/${serverId}/weight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weight: parseInt(weight, 10) }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to update server weight');
  }
  return response.json();
};

export const fetchTelemetry = async () => {
  const response = await fetch(`${API_BASE_URL}/api/telemetry/metrics`);
  if (!response.ok) throw new Error('Failed to fetch telemetry metrics');
  return response.json();
};

export const updateServerHealth = async (serverId, status, reason = 'Manual update via UI') => {
  const response = await fetch(`${API_BASE_URL}/api/servers/${serverId}/health`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_id: serverId,
      status: status.toUpperCase(),
      reason,
    }),
  });
  if (!response.ok) {
    // Fallback to legacy endpoint
    const fallback = await fetch(`${API_BASE_URL}/api/health/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: serverId,
        status: status.toUpperCase(),
        reason,
      }),
    });
    if (!fallback.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update server health');
    }
    return fallback.json();
  }
  return response.json();
};


export const connectWebSocket = (onMessage, onError, onClose) => {
  try {
    const ws = new WebSocket(WS_BASE_URL);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('WebSocket JSON parse error:', e);
      }
    };
    ws.onerror = (err) => {
      if (onError) onError(err);
    };
    ws.onclose = () => {
      if (onClose) onClose();
    };
    return ws;
  } catch (err) {
    if (onError) onError(err);
    return null;
  }
};

// Benchmark Laboratory API
export const startBenchmark = async (config) => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to start benchmark');
  }
  return response.json();
};

export const fetchBenchmarks = async () => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks`);
  if (!response.ok) throw new Error('Failed to fetch benchmarks list');
  return response.json();
};

export const fetchActiveBenchmark = async () => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks/active`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('Failed to fetch active benchmark');
  return response.json();
};

export const fetchBenchmarkDetails = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks/${id}`);
  if (!response.ok) throw new Error('Failed to fetch benchmark details');
  return response.json();
};

export const cancelBenchmark = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks/${id}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to cancel benchmark');
  return response.json();
};

export const deleteBenchmark = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/benchmarks/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete benchmark');
  return response.json();
};

export const getBenchmarkCsvUrl = (id) => `${API_BASE_URL}/api/benchmarks/${id}/export.csv`;
export const getBenchmarkJsonUrl = (id) => `${API_BASE_URL}/api/benchmarks/${id}/export.json`;

