import React from 'react';
import { Zap, Layers, RefreshCw, BarChart2, Shuffle, Sparkles, CheckCircle } from 'lucide-react';

const ALGORITHM_ICONS = {
  round_robin: RefreshCw,
  weighted_round_robin: Layers,
  least_connections: BarChart2,
  least_bandwidth: Zap,
  random: Shuffle,
  adaptive: Sparkles,
};

export default function AlgorithmSelector({
  algorithms,
  activeAlgorithm,
  onSwitchAlgorithm,
}) {
  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
      <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            Dynamic Load Balancing Algorithms
          </h2>
          <p className="text-xs text-slate-400">
            Dynamically switch OpenFlow forwarding logic in real-time without interrupting active traffic flows.
          </p>
        </div>

        <div className="text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30 px-3 py-1 rounded-lg">
          Active: {activeAlgorithm.toUpperCase().replace(/_/g, ' ')}
        </div>
      </div>

      {/* Grid of Algorithm Selection Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {algorithms.map((algo) => {
          const IconComponent = ALGORITHM_ICONS[algo.id] || Zap;
          const isActive = activeAlgorithm === algo.id;

          return (
            <div
              key={algo.id}
              onClick={() => onSwitchAlgorithm(algo.id)}
              className={`p-4 rounded-xl border cursor-pointer transition relative overflow-hidden flex flex-col justify-between ${
                isActive
                  ? 'bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/40'
                  : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-800/50'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`p-2 rounded-lg ${
                        isActive ? 'bg-amber-500 text-slate-950 font-bold' : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      <IconComponent className="w-4 h-4" />
                    </div>
                    <span className="font-bold text-sm text-slate-100">
                      {algo.name ? algo.name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : algo.id}
                    </span>
                  </div>

                  {isActive && <CheckCircle className="w-5 h-5 text-amber-400" />}
                </div>

                <p className="text-xs text-slate-400 leading-relaxed">{algo.description}</p>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-800/80 flex justify-end items-center text-[10px] font-mono">
                <span className={isActive ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                  {isActive ? 'ACTIVE IN SDN FLOWS' : 'Click to Activate'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
