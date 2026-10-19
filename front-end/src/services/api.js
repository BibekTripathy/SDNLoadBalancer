/**
 * SDN Load Balancer API Service
 * Handles REST endpoints and WebSocket real-time event streams.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/ws/events';

// Sent with every request. A free ngrok tunnel answers browser requests with an
// HTML warning page (ERR_NGROK_6024, no CORS headers) unless this header is set;
// any other server, e.g. localhost in dev, simply ignores it.
const DEFAULT_HEADERS = { 'ngrok-skip-browser-warning': 'true' };

/** The one place the dashboard calls the backend: fetch(API_BASE_URL + path) with the default headers. */
export const apiFetch = (path, options = {}) =>
  fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { ...DEFAULT_HEADERS, ...(options.headers || {}) },
  });

/**
 * Fetch a file (image, CSV, ...) through apiFetch and return a blob: URL for it.
 * Needed because <img src> and <a href> cannot send the ngrok header.
 * The caller must URL.revokeObjectURL() it when done.
 */
export const fetchBlobUrl = async (path) => {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`Failed to fetch ${path}`);
  return URL.createObjectURL(await response.blob());
};

/** Download a backend file under the given name (a cross-origin <a download> would be ignored). */
export const downloadFile = async (path, filename) => {
  const url = await fetchBlobUrl(path);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export const fetchControllerStatus = async () => {
  const response = await apiFetch(`/api/controller/status`);
  if (!response.ok) throw new Error('Failed to fetch controller status');
  return response.json();
};

export const fetchAlgorithms = async () => {
  const response = await apiFetch(`/api/controller/algorithms`);
  if (!response.ok) throw new Error('Failed to fetch load balancing algorithms');
  return response.json();
};

export const switchAlgorithm = async (algorithmId) => {
  const response = await apiFetch(`/api/controller/algorithm`, {
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
  const response = await apiFetch(`/api/controller/request`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to trigger request');
  }
  return response.json();
};

export const fetchServers = async () => {
  const response = await apiFetch(`/api/servers`);
  if (!response.ok) {
    // Fallback to legacy endpoint if needed
    const fallback = await apiFetch(`/api/controller/servers`);
    if (!fallback.ok) throw new Error('Failed to fetch server pool');
    return fallback.json();
  }
  return response.json();
};

export const fetchServerSuggest = async () => {
  const response = await apiFetch(`/api/servers/suggest`);
  if (!response.ok) throw new Error('Failed to fetch server suggestion');
  return response.json();
};

export const addServer = async (serverData) => {
  const response = await apiFetch(`/api/servers`, {
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
  const response = await apiFetch(`/api/servers/${serverId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to remove backend server');
  }
  return response.json();
};

export const drainServer = async (serverId) => {
  const response = await apiFetch(`/api/servers/${serverId}/drain`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to drain backend server');
  }
  return response.json();
};

export const updateServerWeight = async (serverId, weight) => {
  const response = await apiFetch(`/api/servers/${serverId}/weight`, {
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
  const response = await apiFetch(`/api/telemetry/metrics`);
  if (!response.ok) throw new Error('Failed to fetch telemetry metrics');
  return response.json();
};

export const updateServerHealth = async (serverId, status, reason = 'Manual update via UI') => {
  const response = await apiFetch(`/api/servers/${serverId}/health`, {
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
    const fallback = await apiFetch(`/api/health/override`, {
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
  const response = await apiFetch(`/api/benchmarks`, {
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
  const response = await apiFetch(`/api/benchmarks`);
  if (!response.ok) throw new Error('Failed to fetch benchmarks list');
  return response.json();
};

export const fetchActiveBenchmark = async () => {
  const response = await apiFetch(`/api/benchmarks/active`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('Failed to fetch active benchmark');
  return response.json();
};

export const fetchBenchmarkDetails = async (id) => {
  const response = await apiFetch(`/api/benchmarks/${id}`);
  if (!response.ok) throw new Error('Failed to fetch benchmark details');
  return response.json();
};

export const cancelBenchmark = async (id) => {
  const response = await apiFetch(`/api/benchmarks/${id}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to cancel benchmark');
  return response.json();
};

export const deleteBenchmark = async (id) => {
  const response = await apiFetch(`/api/benchmarks/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete benchmark');
  return response.json();
};

export const downloadBenchmarkCsv = (id) => downloadFile(`/api/benchmarks/${id}/export.csv`, `benchmark-${id}.csv`);
export const downloadBenchmarkJson = (id) => downloadFile(`/api/benchmarks/${id}/export.json`, `benchmark-${id}.json`);


// TCP Congestion Control Lab API (/api/tcp-lab). The page only DISPLAYS what
// these return; every TCP number is computed by the backend.
const getJson = async (path, what) => {
  const response = await apiFetch(`${path}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to fetch ${what}`);
  return response.json();
};

const postJson = async (path, body, what) => {
  const response = await apiFetch(`${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const detail = typeof err.detail === 'string' ? err.detail : `Failed to ${what}`;
    throw new Error(detail);
  }
  return response.json();
};

export const fetchTcpLabScenarios = () => getJson('/api/tcp-lab/scenarios', 'TCP lab scenarios');
export const fetchTcpLabAnalysis = () => getJson('/api/tcp-lab/analysis', 'TCP lab analysis');
export const fetchTcpLabTimeseries = (scenario, variant, run = 1) =>
  getJson(`/api/tcp-lab/results/${scenario}/${variant}/timeseries?run=${run}`, 'TCP lab time series');
export const startTcpLabSimulation = (body) => postJson('/api/tcp-lab/live/simulate', body, 'start simulation');
export const startTcpLabReplay = (body) => postJson('/api/tcp-lab/live/replay', body, 'start replay');
export const stopTcpLabRun = () => postJson('/api/tcp-lab/live/stop', {}, 'stop run');
export const fetchTcpLabPlot = (name) => fetchBlobUrl(`/api/tcp-lab/analysis/plots/${name}`);
