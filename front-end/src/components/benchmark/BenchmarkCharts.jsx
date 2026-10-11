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
import { Bar, Line } from 'react-chartjs-2';
import { BarChart3, TrendingUp, Activity, PieChart } from 'lucide-react';

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

export default function BenchmarkCharts({ summary = [], runs = [] }) {
  if (!summary || summary.length === 0) return null;

  const algoLabels = summary.map((s) => s.algorithm.replace(/_/g, ' '));

  // Chart 1: Throughput (RPS) Comparison
  const throughputData = {
    labels: algoLabels,
    datasets: [
      {
        label: 'Mean Throughput (req/s)',
        data: summary.map((s) => s.mean_achieved_rps),
        backgroundColor: '#38BDF8',
        borderRadius: 8,
      },
      {
        label: 'Bandwidth (Mbps)',
        data: summary.map((s) => s.mean_throughput_mbps * 10), // scaled for visualization
        backgroundColor: '#818CF8',
        borderRadius: 8,
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
      tooltip: {
        callbacks: {
          label: (context) => {
            if (context.datasetIndex === 1) {
              const actualMbps = (context.raw / 10).toFixed(2);
              return `Bandwidth: ${actualMbps} Mbps`;
            }
            return `${context.dataset.label}: ${context.raw}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#94A3B8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
      },
      y: {
        ticks: { color: '#94A3B8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
        beginAtZero: true,
      },
    },
  };

  // Chart 2: Latency Comparison (Mean vs p95)
  const latencyData = {
    labels: algoLabels,
    datasets: [
      {
        label: 'Mean Latency (ms)',
        data: summary.map((s) => s.mean_latency_ms),
        backgroundColor: '#34D399',
        borderRadius: 8,
      },
      {
        label: 'p95 Tail Latency (ms)',
        data: summary.map((s) => s.p95_latency_ms),
        backgroundColor: '#F59E0B',
        borderRadius: 8,
      },
    ],
  };

  // Chart 3: Request Distribution across Servers (Stacked Bar)
  const distributionData = {
    labels: algoLabels,
    datasets: [
      {
        label: 'Server 1',
        data: summary.map((s) => s.aggregate_distribution?.server1 || 0),
        backgroundColor: '#38BDF8',
      },
      {
        label: 'Server 2',
        data: summary.map((s) => s.aggregate_distribution?.server2 || 0),
        backgroundColor: '#818CF8',
      },
      {
        label: 'Server 3',
        data: summary.map((s) => s.aggregate_distribution?.server3 || 0),
        backgroundColor: '#34D399',
      },
    ],
  };

  const stackedOptions = {
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
        stacked: true,
        ticks: { color: '#94A3B8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
      },
      y: {
        stacked: true,
        ticks: { color: '#94A3B8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
        beginAtZero: true,
      },
    },
  };

  // Chart 4: Time Series (from first run if available)
  const firstRunWithSeries = runs.find((r) => r.time_series && r.time_series.length > 0);
  const timeLabels = firstRunWithSeries ? firstRunWithSeries.time_series.map((t) => `${t.elapsed}s`) : [];
  const timeData = {
    labels: timeLabels,
    datasets: [
      {
        label: `${firstRunWithSeries?.algorithm || 'Active Algorithm'} RPS`,
        data: firstRunWithSeries ? firstRunWithSeries.time_series.map((t) => t.rps) : [],
        borderColor: '#38BDF8',
        backgroundColor: 'rgba(56, 189, 248, 0.1)',
        tension: 0.3,
        fill: true,
        yAxisID: 'y',
      },
      {
        label: 'Latency (ms)',
        data: firstRunWithSeries ? firstRunWithSeries.time_series.map((t) => t.latency_ms) : [],
        borderColor: '#F59E0B',
        backgroundColor: 'rgba(245, 158, 11, 0.1)',
        tension: 0.3,
        yAxisID: 'y1',
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
        ticks: { color: '#94A3B8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
      },
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        ticks: { color: '#38BDF8', font: { family: 'monospace', size: 10 } },
        grid: { color: '#1E293B' },
        beginAtZero: true,
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'right',
        ticks: { color: '#F59E0B', font: { family: 'monospace', size: 10 } },
        grid: { drawOnChartArea: false },
        beginAtZero: true,
      },
    },
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Chart 1 */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Activity className="w-4 h-4 text-sky-400" />
            Throughput by Algorithm
          </h3>
          <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
            req/s comparison
          </span>
        </div>
        <div className="h-64 relative">
          <Bar data={throughputData} options={barOptions} />
        </div>
      </div>

      {/* Chart 2 */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            Response Latency (Mean & p95)
          </h3>
          <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
            Tail Latency in ms
          </span>
        </div>
        <div className="h-64 relative">
          <Bar data={latencyData} options={barOptions} />
        </div>
      </div>

      {/* Chart 3 */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <PieChart className="w-4 h-4 text-indigo-400" />
            Backend Load Distribution (Server 1-3)
          </h3>
          <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
            Total Requests
          </span>
        </div>
        <div className="h-64 relative">
          <Bar data={distributionData} options={stackedOptions} />
        </div>
      </div>

      {/* Chart 4 */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-amber-400" />
            Run Timeline: RPS & Latency Over Time
          </h3>
          <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
            Temporal Profile
          </span>
        </div>
        <div className="h-64 relative">
          {timeLabels.length > 0 ? (
            <Line data={timeData} options={lineOptions} />
          ) : (
            <div className="h-full flex items-center justify-center text-xs font-mono text-slate-500">
              Time-series profile available once test completes.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
