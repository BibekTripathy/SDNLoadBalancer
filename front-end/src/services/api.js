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

export const fetchServers = async () => {
  const response = await fetch(`${API_BASE_URL}/api/controller/servers`);
  if (!response.ok) throw new Error('Failed to fetch server pool');
  return response.json();
};

export const fetchTelemetry = async () => {
  const response = await fetch(`${API_BASE_URL}/api/telemetry/metrics`);
  if (!response.ok) throw new Error('Failed to fetch telemetry metrics');
  return response.json();
};

export const updateServerHealth = async (serverId, status, reason = 'Manual update via UI') => {
  const response = await fetch(`${API_BASE_URL}/api/health/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_id: serverId,
      status: status.toUpperCase(),
      reason,
    }),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to update server health');
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

