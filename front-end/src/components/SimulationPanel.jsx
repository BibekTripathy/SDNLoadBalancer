import React from 'react';
import { Sliders, AlertTriangle, Power, Terminal, Zap, ShieldAlert, Play, Pause } from 'lucide-react';

export default function SimulationPanel({
  trafficRate,
  setTrafficRate,
  servers,
  onToggleServerHealth,
  onDrainServer,
  trafficLogs,
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      {/* 1. Traffic Intensity Controls */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-sky-400" />
              Traffic Load Generator
            </h3>
            <span className="text-xs font-mono text-sky-400 bg-sky-950 px-2 py-0.5 rounded border border-sky-800">
              {trafficRate} req/s
            </span>
          </div>

          <p className="text-xs text-slate-400 mb-4">
            Simulate incoming client traffic requests to evaluate real-time load distribution.
          </p>

          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={trafficRate}
            onChange={(e) => setTrafficRate(parseInt(e.target.value, 10))}
            className="w-full accent-sky-400 bg-slate-800 h-2 rounded-lg cursor-pointer mb-4"
          />

          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'Pause', val: 0 },
              { label: 'Low', val: 5 },
              { label: 'Med', val: 20 },
              { label: 'High', val: 50 },
            ].map((preset) => (
              <button
                key={preset.label}
                onClick={() => setTrafficRate(preset.val)}
                className={`py-1.5 rounded-lg text-xs font-mono border transition ${
                  trafficRate === preset.val
                    ? 'bg-sky-500/20 border-sky-500 text-sky-300 font-bold'
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-500 font-mono">
          Traffic packets are routed via OpenFlow rules to active backend ports.
        </div>
      </div>

      {/* 2. Server Fault & Failure Simulator */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Server Fault Injection
          </h3>
          <span className="text-[10px] text-slate-400 font-mono">Failover Test</span>
        </div>

        <p className="text-xs text-slate-400 mb-3">
          Simulate server failures and draining to observe how the SDN controller dynamically reroutes traffic without packet drops.
        </p>

        <div className="space-y-2.5 max-h-60 overflow-y-auto pr-1 custom-scrollbar">
          {servers.map((srv) => {
            const srvId = srv.id || srv.server_id;
            const isHealthy = srv.status === 'HEALTHY';
            const isDraining = srv.status === 'DRAINING';

            return (
              <div
                key={srvId}
                className="flex items-center justify-between p-2.5 bg-slate-900/80 rounded-xl border border-slate-800"
              >
                <div>
                  <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                    <span>{srvId}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                        isHealthy
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : isDraining
                          ? 'bg-amber-950 text-amber-400 border border-amber-800'
                          : 'bg-red-950 text-red-400 border border-red-800'
                      }`}
                    >
                      {srv.status}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-slate-400">
                    {srv.ip} • Port {srv.switch_port}
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  {onDrainServer && isHealthy && (
                    <button
                      onClick={() => onDrainServer(srvId)}
                      title="Drain active connections"
                      className="px-2 py-1 rounded-lg text-[10px] font-mono border bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/30 transition"
                    >
                      Drain
                    </button>
                  )}

                  <button
                    onClick={() => onToggleServerHealth(srvId, isHealthy ? 'DOWN' : 'HEALTHY')}
                    className={`px-2.5 py-1 rounded-lg text-xs font-mono border flex items-center gap-1 transition ${
                      isHealthy
                        ? 'bg-red-500/10 hover:bg-red-500/20 text-red-400 border-red-500/30'
                        : 'bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                    }`}
                  >
                    <Power className="w-3 h-3" />
                    {isHealthy ? 'Fail' : 'Recover'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>


      {/* 3. Live Traffic & Event Terminal Console */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl flex flex-col h-80">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-400" />
            Live Event Stream
          </h3>
          <span className="text-[10px] font-mono text-slate-500">Auto-Scroll</span>
        </div>

        <div className="flex-1 min-h-0 bg-slate-950 rounded-xl p-3 border border-slate-900 font-mono text-[11px] overflow-y-auto space-y-1.5 custom-scrollbar">
          {trafficLogs.length === 0 ? (
            <div className="text-slate-600 italic">No events logged yet...</div>
          ) : (
            trafficLogs.map((log) => (
              <div key={log.id} className="leading-tight flex items-start gap-2">
                <span className="text-slate-500 flex-shrink-0">[{log.timestamp}]</span>
                <span
                  className={
                    log.type === 'error'
                      ? 'text-red-400 font-bold'
                      : log.type === 'warning'
                      ? 'text-amber-400 font-semibold'
                      : log.type === 'success'
                      ? 'text-emerald-400'
                      : 'text-sky-300'
                  }
                >
                  {log.msg}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
