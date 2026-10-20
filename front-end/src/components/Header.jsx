import React from 'react';
import { Network, RefreshCw, Radio } from 'lucide-react';

export default function Header({ isLiveConnected, simulationMode, setSimulationMode }) {
  return (
    <header className="sdn-header glass-panel border-b border-slate-800 px-6 py-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 sticky top-0 z-40">
      {/* Brand & Logo */}
      <div className="flex items-center gap-3 whitespace-nowrap">
        <div className="p-2.5 bg-sky-500/10 border border-sky-500/30 rounded-xl text-sky-400 shadow-lg shadow-sky-500/10">
          <Network className="w-7 h-7 animate-pulse" />
        </div>
        <h1 className="text-xl font-bold whitespace-nowrap bg-gradient-to-r from-sky-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
          SDN Dynamic Load Balancer
        </h1>
      </div>


      {/* Live vs Simulation mode */}
      <div className="flex items-center gap-3 whitespace-nowrap">

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
