import React from 'react';
import { X, Server, Activity, Power, Wifi, ShieldAlert, Cpu } from 'lucide-react';

export default function ServerDetailModal({
  server,
  metrics,
  onClose,
  onToggleHealth,
  onUpdateWeight,
}) {
  if (!server) return null;

  const isHealthy = server.status === 'HEALTHY';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div
              className={`p-2.5 rounded-xl border ${
                isHealthy
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-red-500/10 text-red-400 border-red-500/30'
              }`}
            >
              <Server className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100">{server.id} Configuration & Telemetry</h3>
              <p className="text-xs font-mono text-slate-400">
                IP: {server.ip} • Switch Port: {server.switch_port}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-100 bg-slate-800 hover:bg-slate-700 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 text-xs font-mono">
          {/* Quick Status Pill */}
          <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-800">
            <span className="text-slate-400">HEALTH STATUS</span>
            <span
              className={`px-3 py-1 rounded-lg font-bold border ${
                isHealthy
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                  : 'bg-red-500/20 text-red-400 border-red-500/40 animate-pulse'
              }`}
            >
              {server.status}
            </span>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">BANDWIDTH</div>
              <div className="text-base font-bold text-sky-400 mt-1">
                {isHealthy ? `${metrics?.bandwidth_mbps || 0} Mbps` : '0 Mbps'}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">ACTIVE SESSIONS</div>
              <div className="text-base font-bold text-emerald-400 mt-1">
                {isHealthy ? metrics?.active_connections || 0 : 0}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">PACKET RATE</div>
              <div className="text-base font-bold text-purple-400 mt-1">
                {isHealthy ? `${metrics?.packet_rate || 0} pkt/s` : '0 pkt/s'}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">LATENCY (RTT)</div>
              <div className="text-base font-bold text-amber-400 mt-1">
                {isHealthy ? `${metrics?.latency_ms || 1.5} ms` : 'N/A'}
              </div>
            </div>
          </div>

          {/* Weight Control for Weighted Round Robin */}
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
            <div className="flex justify-between items-center text-slate-300">
              <span>WEIGHT CAPACITY</span>
              <span className="text-sky-400 font-bold text-sm">{server.weight}</span>
            </div>
            <p className="text-[10px] text-slate-500 font-sans">
              Used by Weighted Round Robin and Adaptive load balancers to proportion traffic share.
            </p>
            <input
              type="range"
              min="1"
              max="10"
              value={server.weight}
              onChange={(e) => onUpdateWeight(server.id, e.target.value)}
              className="w-full accent-sky-400 bg-slate-800 h-2 rounded-lg cursor-pointer"
            />
          </div>

          {/* Actions */}
          <div className="pt-2">
            <button
              onClick={() => {
                onToggleHealth(server.id, isHealthy ? 'DOWN' : 'HEALTHY');
                onClose();
              }}
              className={`w-full py-2.5 rounded-xl font-bold flex items-center justify-center gap-2 border transition ${
                isHealthy
                  ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border-red-500/30'
                  : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              }`}
            >
              <Power className="w-4 h-4" />
              {isHealthy ? 'Simulate Server Failure (DOWN)' : 'Bring Server Back Online (HEALTHY)'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
