import React, { useState } from 'react';
import {
  X,
  Server,
  Activity,
  Power,
  Wifi,
  ShieldAlert,
  Cpu,
  Clock,
  Trash2,
  AlertTriangle,
} from 'lucide-react';

export default function ServerDetailModal({
  server,
  metrics,
  onClose,
  onToggleHealth,
  onUpdateWeight,
  onDrainServer,
  onRemoveServer,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!server) return null;

  const srvId = server.id || server.server_id;
  const isHealthy = server.status === 'HEALTHY';
  const isDraining = server.status === 'DRAINING';
  const isDown = server.status === 'DOWN';
  const activeConns = metrics?.active_connections || 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div
              className={`p-2.5 rounded-xl border ${
                isHealthy
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : isDraining
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  : 'bg-red-500/10 text-red-400 border-red-500/30'
              }`}
            >
              <Server className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100">{srvId} Configuration & Telemetry</h3>
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
                  : isDraining
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
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
                {isHealthy || isDraining ? `${metrics?.bandwidth_mbps || 0} Mbps` : '0 Mbps'}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">ACTIVE SESSIONS</div>
              <div className="text-base font-bold text-emerald-400 mt-1">
                {isHealthy || isDraining ? activeConns : 0}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">PACKET RATE</div>
              <div className="text-base font-bold text-purple-400 mt-1">
                {isHealthy || isDraining ? `${metrics?.packet_rate || 0} pkt/s` : '0 pkt/s'}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
              <div className="text-slate-500 text-[10px]">LATENCY (RTT)</div>
              <div className="text-base font-bold text-amber-400 mt-1">
                {isHealthy || isDraining ? `${metrics?.latency_ms || 1.5} ms` : 'N/A'}
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
              max="20"
              value={server.weight}
              onChange={(e) => onUpdateWeight && onUpdateWeight(srvId, e.target.value)}
              className="w-full accent-sky-400 bg-slate-800 h-2 rounded-lg cursor-pointer"
            />
          </div>

          {/* Health & Failure Management Buttons */}
          <div className="grid grid-cols-2 gap-2.5 pt-1">
            <button
              onClick={() => {
                onToggleHealth && onToggleHealth(srvId, isHealthy ? 'DOWN' : 'HEALTHY');
                onClose();
              }}
              className={`py-2 rounded-xl font-bold flex items-center justify-center gap-1.5 border transition text-xs ${
                isHealthy
                  ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border-red-500/30'
                  : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              }`}
            >
              <Power className="w-3.5 h-3.5" />
              {isHealthy ? 'Simulate DOWN' : 'Recover (HEALTHY)'}
            </button>

            {onDrainServer && (
              <button
                onClick={() => {
                  onDrainServer(srvId);
                  onClose();
                }}
                disabled={isDraining}
                className={`py-2 rounded-xl font-bold flex items-center justify-center gap-1.5 border transition text-xs ${
                  isDraining
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 opacity-75 cursor-not-allowed'
                    : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30'
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                {isDraining ? 'Already Draining' : 'Drain Connections'}
              </button>
            )}
          </div>

          {/* Removal Confirmation Dialog */}
          {onRemoveServer && (
            <div className="pt-2 border-t border-slate-800">
              {confirmDelete ? (
                <div className="p-3 bg-red-950/70 border border-red-800/80 rounded-xl space-y-2">
                  <div className="flex items-start gap-2 text-red-300 text-[11px]">
                    <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <span>
                      Remove <strong>{srvId}</strong>?
                      {activeConns > 0 && (
                        <span className="block text-red-400 font-bold mt-0.5">
                          Warning: {activeConns} active connection(s) will be terminated!
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[10px]"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        onRemoveServer(srvId);
                        onClose();
                      }}
                      className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded-lg text-[10px] font-bold flex items-center gap-1 shadow"
                    >
                      <Trash2 className="w-3 h-3" />
                      Confirm Delete
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  className="w-full py-2 bg-slate-900 hover:bg-red-950/40 text-red-400 hover:text-red-300 border border-slate-800 hover:border-red-800/50 rounded-xl font-bold flex items-center justify-center gap-1.5 transition text-xs"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Remove Server from Pool
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

