import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import { Activity, BarChart3, TrendingUp, Cpu, Server, Wifi } from 'lucide-react';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export default function MetricsDashboard({
  metricsHistory,
  currentMetrics,
  servers,
  controllerStatus,
}) {
  // Chart 1: Bandwidth Over Time (Line Chart)
  const lineLabels = metricsHistory.map((h) => h.time);
  const lineData = {
    labels: lineLabels.length ? lineLabels : ['00:00', '00:01', '00:02'],
    datasets: [
      {
        label: 'Server 1 (Mbps)',
        data: metricsHistory.map((h) => h.server1_bw),
        borderColor: '#38BDF8',
        backgroundColor: 'rgba(56, 189, 248, 0.1)',
        tension: 0.3,
        fill: true,
      },
      {
        label: 'Server 2 (Mbps)',
        data: metricsHistory.map((h) => h.server2_bw),
        borderColor: '#818CF8',
        backgroundColor: 'rgba(129, 140, 248, 0.1)',
        tension: 0.3,
        fill: true,
      },
      {
        label: 'Server 3 (Mbps)',
        data: metricsHistory.map((h) => h.server3_bw),
        borderColor: '#34D399',
        backgroundColor: 'rgba(52, 211, 153, 0.1)',
        tension: 0.3,
        fill: true,
      },
    ],
  };

  const lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: { color: '#94A3B8', font: { family: 'monospace', size: 11 } },
      },
    },
    scales: {
      x: {
        ticks: { color: '#64748B', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
      },
      y: {
        ticks: { color: '#64748B', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
        beginAtZero: true,
      },
    },
  };

  // Chart 2: Active Connections & Packet Rate Bar Chart
  const serverNames = servers.map((s) => s.id);
  const barData = {
    labels: serverNames,
    datasets: [
      {
        label: 'Active TCP Connections',
        data: servers.map((s) => currentMetrics[s.id]?.active_connections || 0),
        backgroundColor: '#38BDF8',
        borderRadius: 6,
      },
      {
        label: 'Packet Rate (pkt/s)',
        data: servers.map((s) => currentMetrics[s.id]?.packet_rate || 0),
        backgroundColor: '#A855F7',
        borderRadius: 6,
      },
    ],
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: { color: '#94A3B8', font: { family: 'monospace', size: 11 } },
      },
    },
    scales: {
      x: {
        ticks: { color: '#64748B', font: { family: 'monospace', size: 11 } },
        grid: { color: '#1E293B' },
      },
      y: {
        ticks: { color: '#64748B', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
        beginAtZero: true,
      },
    },
  };

  // Compute aggregate stats
  const totalBw = Object.values(currentMetrics)
    .reduce((acc, m) => acc + (m.bandwidth_mbps || 0), 0)
    .toFixed(2);
  const totalConns = Object.values(currentMetrics).reduce((acc, m) => acc + (m.active_connections || 0), 0);
  const avgLatency = (
    Object.values(currentMetrics).reduce((acc, m) => acc + (m.latency_ms || 0), 0) /
    (servers.length || 1)
  ).toFixed(2);

  return (
    <div className="space-y-5">
      {/* Top Stat Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-mono">TOTAL THROUGHPUT</div>
            <div className="text-2xl font-extrabold text-sky-400 font-mono mt-1">{totalBw} Mbps</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Aggregated pool bandwidth</div>
          </div>
          <div className="p-3 bg-sky-500/10 text-sky-400 rounded-xl border border-sky-500/20">
            <Wifi className="w-6 h-6" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-mono">ACTIVE CONNECTIONS</div>
            <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">{totalConns}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Distributed TCP sessions</div>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
            <Activity className="w-6 h-6" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-mono">AVG RESPONSE LATENCY</div>
            <div className="text-2xl font-extrabold text-indigo-400 font-mono mt-1">{avgLatency} ms</div>
            <div className="text-[10px] text-slate-500 mt-0.5">ICMP/TCP RTT via OpenFlow</div>
          </div>
          <div className="p-3 bg-indigo-500/10 text-indigo-400 rounded-xl border border-indigo-500/20">
            <TrendingUp className="w-6 h-6" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-mono">SERVER POOL HEALTH</div>
            <div className="text-2xl font-extrabold text-purple-400 font-mono mt-1">
              {controllerStatus.healthy_servers_count} / {controllerStatus.total_servers_count}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">Active backend instances</div>
          </div>
          <div className="p-3 bg-purple-500/10 text-purple-400 rounded-xl border border-purple-500/20">
            <Server className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Real-time Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <Activity className="w-4 h-4 text-sky-400" />
              Bandwidth Consumption Over Time (Mbps)
            </h3>
            <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
              Live Stream
            </span>
          </div>
          <div className="h-64 relative">
            <Line data={lineData} options={lineOptions} />
          </div>
        </div>

        <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-purple-400" />
              Connections & Packet Rate per Server
            </h3>
            <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
              Real-time Distribution
            </span>
          </div>
          <div className="h-64 relative">
            <Bar data={barData} options={barOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
