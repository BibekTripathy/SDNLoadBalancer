import React from 'react';
import { Network, Activity, Cpu, ShieldCheck, Zap, RefreshCw, Radio } from 'lucide-react';

export default function Header({
  controllerStatus,
  isLiveConnected,
  simulationMode,
  setSimulationMode,
  activeAlgorithm,
  onOpenFlowRules,
}) {
  return (
    <header className="sdn-header glass-panel border-b border-slate-800 px-6 py-4 flex flex-col md:flex-row md:flex-wrap items-center justify-between gap-x-4 gap-y-3 sticky top-0 z-40">
      {/* Brand & Logo */}
      <div className="flex items-center gap-3 whitespace-nowrap">
        <div className="p-2.5 bg-sky-500/10 border border-sky-500/30 rounded-xl text-sky-400 shadow-lg shadow-sky-500/10">
          <Network className="w-7 h-7 animate-pulse" />
        </div>
        <h1 className="text-xl font-bold whitespace-nowrap bg-gradient-to-r from-sky-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
          SDN Dynamic Load Balancer
        </h1>
      </div>

      {/* Controller Quick Stats */}
      <div className="flex items-center gap-4 text-xs font-mono whitespace-nowrap">
        <div className="bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-indigo-400" />
          <span className="text-slate-400">Controller:</span>
          <span className="text-emerald-400 font-bold">{controllerStatus.controller_status}</span>
        </div>

        <div className="bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="text-slate-400">Algorithm:</span>
          <span className="text-amber-300 font-bold uppercase">{activeAlgorithm.replace('_', ' ')}</span>
        </div>

        <div className="bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2">
          <Activity className="w-4 h-4 text-sky-400" />
          <span className="text-slate-400">Requests:</span>
          <span className="text-sky-300 font-bold">{controllerStatus.total_requests?.toLocaleString()}</span>
        </div>
      </div>

      {/* Status Badges & Controls */}
      <div className="flex items-center gap-3 whitespace-nowrap">
        <button
          onClick={onOpenFlowRules}
          className="px-3 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 rounded-lg text-xs font-medium transition flex items-center gap-1.5 shadow-sm"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          Flow Table
        </button>

        {/* Live vs Simulation indicator badge */}
        <div
          onClick={() => setSimulationMode(!simulationMode)}
          title="Click to toggle Simulation Mode"
          className={`cursor-pointer px-3 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-2 transition ${
            isLiveConnected
              ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400 shadow-emerald-500/10 shadow-sm'
              : 'bg-amber-500/10 border-amber-500/40 text-amber-400 shadow-amber-500/10 shadow-sm'
          }`}
        >
          <Radio className={`w-3.5 h-3.5 ${isLiveConnected ? 'animate-pulse text-emerald-400' : 'text-amber-400'}`} />
          <span>{isLiveConnected ? 'LIVE FASTAPI API' : 'SIMULATION DEMO MODE'}</span>
          <RefreshCw className="w-3 h-3 text-slate-400 ml-1 hover:rotate-180 transition-transform" />
        </div>
      </div>
    </header>
  );
}
