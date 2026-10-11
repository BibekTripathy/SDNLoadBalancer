import React, { useState } from 'react';
import { HelpCircle, ChevronDown, ChevronRight, Award, Server } from 'lucide-react';

export default function AlgorithmComparisonTable({ summary = [], runs = [], isSimulated = false }) {
  const [expandedAlgo, setExpandedAlgo] = useState(null);

  if (!summary || summary.length === 0) {
    return (
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 text-center text-slate-500 font-mono text-xs">
        No completed algorithm results available yet. Run a benchmark experiment above.
      </div>
    );
  }

  // Find best performing algorithm by achieved RPS
  const bestRpsAlgo = [...summary].sort((a, b) => b.mean_achieved_rps - a.mean_achieved_rps)[0]?.algorithm;
  // Find best performing algorithm by lowest p95 latency
  const bestLatAlgo = [...summary].sort((a, b) => a.p95_latency_ms - b.p95_latency_ms)[0]?.algorithm;

  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide flex items-center gap-2">
            Algorithm Performance Comparison
            {isSimulated && (
              <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded font-mono font-normal">
                Simulated Run
              </span>
            )}
          </h3>
          <p className="text-[11px] text-slate-400">
            Steady-state measurements excluding warm-up period. Click an algorithm row to view repetition breakdowns.
          </p>
        </div>

        {/* Fairness Explanation Tooltip Note */}
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400 bg-slate-900/80 px-2.5 py-1 rounded-lg border border-slate-800">
          <HelpCircle className="w-3.5 h-3.5 text-sky-400" />
          <span>
            Jain's Index (J): <span className="text-slate-300">1.0 = equal load balance</span>
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
              <th className="py-2.5 px-3">Algorithm</th>
              <th className="py-2.5 px-3 text-right">Throughput (RPS)</th>
              <th className="py-2.5 px-3 text-right">Bandwidth</th>
              <th className="py-2.5 px-3 text-right">Mean Latency</th>
              <th className="py-2.5 px-3 text-right">p95 Latency</th>
              <th className="py-2.5 px-3 text-right">Error Rate</th>
              <th className="py-2.5 px-3">Backend Distribution (s1 / s2 / s3)</th>
              <th className="py-2.5 px-3 text-right">Jain's Index</th>
              <th className="py-2.5 px-3 text-right">Recovery</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {summary.map((item) => {
              const isExpanded = expandedAlgo === item.algorithm;
              const algoRuns = runs.filter((r) => r.algorithm === item.algorithm);
              const dist = item.aggregate_distribution || {};
              const s1 = dist.server1 || 0;
              const s2 = dist.server2 || 0;
              const s3 = dist.server3 || 0;
              const totalReqs = s1 + s2 + s3 || 1;

              const isBestRps = item.algorithm === bestRpsAlgo;
              const isBestLat = item.algorithm === bestLatAlgo;

              return (
                <React.Fragment key={item.algorithm}>
                  <tr
                    onClick={() => setExpandedAlgo(isExpanded ? null : item.algorithm)}
                    className="hover:bg-slate-900/50 cursor-pointer transition"
                  >
                    <td className="py-3 px-3 font-bold text-slate-200 flex items-center gap-1.5">
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                      )}
                      <span>{item.algorithm.replace(/_/g, ' ')}</span>
                      {isBestRps && (
                        <span title="Highest Throughput" className="text-sky-400">
                          <Award className="w-3.5 h-3.5" />
                        </span>
                      )}
                      {isBestLat && (
                        <span title="Lowest p95 Latency" className="text-emerald-400">
                          <Award className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </td>

                    <td className="py-3 px-3 text-right text-sky-400 font-bold">
                      {item.mean_achieved_rps} <span className="text-[10px] text-slate-500 font-normal">req/s</span>
                    </td>

                    <td className="py-3 px-3 text-right text-indigo-300">
                      {item.mean_throughput_mbps} <span className="text-[10px] text-slate-500">Mbps</span>
                    </td>

                    <td className="py-3 px-3 text-right text-slate-300">
                      {item.mean_latency_ms} <span className="text-[10px] text-slate-500">ms</span>
                    </td>

                    <td className="py-3 px-3 text-right text-amber-300 font-bold">
                      {item.p95_latency_ms} <span className="text-[10px] text-slate-500 font-normal">ms</span>
                    </td>

                    <td className="py-3 px-3 text-right">
                      <span
                        className={
                          item.mean_error_rate_pct > 0
                            ? 'text-rose-400 font-bold'
                            : 'text-emerald-400'
                        }
                      >
                        {item.mean_error_rate_pct}%
                      </span>
                    </td>

                    {/* Backend Distribution Visualizer */}
                    <td className="py-3 px-3 min-w-[180px]">
                      <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mb-1">
                        <span>s1: {s1}</span>
                        <span>•</span>
                        <span>s2: {s2}</span>
                        <span>•</span>
                        <span>s3: {s3}</span>
                      </div>
                      <div className="w-full bg-slate-950 h-2 rounded-full flex overflow-hidden border border-slate-800">
                        <div
                          style={{ width: `${(s1 / totalReqs) * 100}%` }}
                          title={`Server 1: ${s1} reqs (${Math.round((s1 / totalReqs) * 100)}%)`}
                          className="bg-sky-400 h-full"
                        />
                        <div
                          style={{ width: `${(s2 / totalReqs) * 100}%` }}
                          title={`Server 2: ${s2} reqs (${Math.round((s2 / totalReqs) * 100)}%)`}
                          className="bg-indigo-400 h-full"
                        />
                        <div
                          style={{ width: `${(s3 / totalReqs) * 100}%` }}
                          title={`Server 3: ${s3} reqs (${Math.round((s3 / totalReqs) * 100)}%)`}
                          className="bg-emerald-400 h-full"
                        />
                      </div>
                    </td>

                    <td className="py-3 px-3 text-right font-bold text-slate-200">
                      <span
                        className={
                          item.jains_fairness_index >= 0.95
                            ? 'text-emerald-400'
                            : item.jains_fairness_index >= 0.8
                            ? 'text-sky-300'
                            : 'text-amber-400'
                        }
                      >
                        {item.jains_fairness_index.toFixed(3)}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right text-slate-400">
                      {item.recovery_time_sec !== null && item.recovery_time_sec !== undefined ? (
                        <span className="text-purple-300 font-bold">{item.recovery_time_sec}s</span>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>

                  {/* Expanded Individual Repetitions Sub-Table */}
                  {isExpanded && algoRuns.length > 0 && (
                    <tr className="bg-slate-950/80">
                      <td colSpan={9} className="py-3 px-4">
                        <div className="text-[11px] text-slate-400 font-semibold mb-2">
                          Individual Repetitions ({algoRuns.length} runs):
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-[10px]">
                          {algoRuns.map((r) => (
                            <div
                              key={r.repetition}
                              className="p-2.5 rounded-lg border border-slate-800/80 bg-slate-900/40 space-y-1"
                            >
                              <div className="font-bold text-slate-300">Run #{r.repetition}</div>
                              <div className="text-slate-400 flex justify-between">
                                <span>Throughput:</span>
                                <span className="text-sky-400 font-mono">{r.achieved_rps} req/s</span>
                              </div>
                              <div className="text-slate-400 flex justify-between">
                                <span>Latency (Mean / p95):</span>
                                <span className="text-slate-200 font-mono">
                                  {r.mean_latency_ms}ms / {r.p95_latency_ms}ms
                                </span>
                              </div>
                              <div className="text-slate-400 flex justify-between">
                                <span>Fairness Index:</span>
                                <span className="text-emerald-400 font-mono">{r.jains_fairness_index}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="text-[10px] text-slate-500 font-mono border-t border-slate-800/60 pt-2 flex items-center justify-between">
        <span>* Jain's Fairness Index measures equal distribution across available servers.</span>
        <span>** Weighted algorithms intentionally skew requests proportional to assigned capacity.</span>
      </div>
    </div>
  );
}
