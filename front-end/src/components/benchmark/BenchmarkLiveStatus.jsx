import React from 'react';
import { Activity, StopCircle, Radio, Clock, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

export default function BenchmarkLiveStatus({ benchmark, onCancel }) {
  if (!benchmark) return null;

  const {
    id,
    name,
    status,
    current_algorithm,
    current_repetition,
    progress_percent = 0,
    live_stats = {},
    is_simulated,
    error_message,
  } = benchmark;

  const isRunning = status === 'running' || status === 'preparing';

  const getStatusBadge = () => {
    switch (status) {
      case 'preparing':
        return (
          <span className="bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 animate-spin" /> Preparing
          </span>
        );
      case 'running':
        return (
          <span className="bg-sky-500/20 text-sky-300 border border-sky-500/30 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
            Running
          </span>
        );
      case 'completed':
        return (
          <span className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> Completed
          </span>
        );
      case 'failed':
        return (
          <span className="bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5">
            <XCircle className="w-3.5 h-3.5" /> Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="bg-slate-700/50 text-slate-300 border border-slate-600 px-2.5 py-1 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Cancelled
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-slate-900 border border-slate-800 rounded-xl text-sky-400">
            <Activity className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-100">{name}</h3>
              <span className="text-[11px] font-mono text-slate-500">#{id}</span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-2 mt-0.5 font-mono">
              <span>Status:</span>
              {getStatusBadge()}
              <span className="text-slate-600">•</span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  is_simulated
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                }`}
              >
                {is_simulated ? 'SIMULATED DATA' : 'LIVE MININET TRAFFIC'}
              </span>
            </p>
          </div>
        </div>

        {isRunning && (
          <button
            type="button"
            onClick={() => onCancel(id)}
            className="px-4 py-2 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/40 rounded-xl text-xs font-bold font-mono transition flex items-center gap-2 self-start sm:self-auto shadow-sm"
          >
            <StopCircle className="w-4 h-4 text-rose-400" />
            Cancel Benchmark
          </button>
        )}
      </div>

      {error_message && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-xl text-xs font-mono">
          Error: {error_message}
        </div>
      )}

      {/* Progress Bar */}
      <div>
        <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-1.5">
          <span>
            {current_algorithm ? (
              <span className="text-sky-300 font-bold uppercase">
                Testing {current_algorithm.replace('_', ' ')} (Rep {current_repetition || 1})
              </span>
            ) : (
              'Experiment Progress'
            )}
          </span>
          <span className="text-sky-400 font-bold">{progress_percent}%</span>
        </div>
        <div className="w-full bg-slate-950 h-2.5 rounded-full overflow-hidden border border-slate-800">
          <div
            className={`h-full transition-all duration-300 ${
              status === 'completed'
                ? 'bg-emerald-500'
                : status === 'failed'
                ? 'bg-rose-500'
                : 'bg-gradient-to-r from-sky-500 via-indigo-500 to-purple-500 animate-pulse'
            }`}
            style={{ width: `${progress_percent}%` }}
          />
        </div>
      </div>

      {/* Live Stream Statistics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
        <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] font-mono text-slate-500 uppercase">Current Throughput</div>
          <div className="text-lg font-mono font-extrabold text-sky-400 mt-0.5">
            {live_stats.current_rps || 0} <span className="text-xs font-normal text-slate-400">req/s</span>
          </div>
        </div>

        <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] font-mono text-slate-500 uppercase">Live Latency</div>
          <div className="text-lg font-mono font-extrabold text-indigo-400 mt-0.5">
            {live_stats.current_latency_ms || 0} <span className="text-xs font-normal text-slate-400">ms</span>
          </div>
        </div>

        <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] font-mono text-slate-500 uppercase">Requests (OK / Fail)</div>
          <div className="text-lg font-mono font-extrabold text-emerald-400 mt-0.5">
            {live_stats.successful_requests || 0}
            <span className="text-xs font-normal text-rose-400 ml-1">/ {live_stats.failed_requests || 0}</span>
          </div>
        </div>

        <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800">
          <div className="text-[10px] font-mono text-slate-500 uppercase">Active Target Node</div>
          <div className="text-lg font-mono font-extrabold text-purple-400 mt-0.5 flex items-center gap-1.5">
            <Radio className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
            {live_stats.current_active_server || 'Waiting...'}
          </div>
        </div>
      </div>
    </div>
  );
}
