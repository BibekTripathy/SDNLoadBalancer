import React from 'react';
import { Table2 } from 'lucide-react';
import SourceBadge from './SourceBadge';
import { ALGORITHM_COLORS, ALGORITHM_LABELS, SIM_ALGORITHMS, formatStats } from './tcpLabStyle';

// [metric key, label, decimals]; the statistics come from analysis.json
const METRICS = [
  ['goodput_mbps', 'goodput (Mbit/s)', 2],
  ['throughput_mbps', 'throughput (Mbit/s)', 2],
  ['retransmissions', 'retransmissions', 1],
  ['spurious_retransmissions', 'of which spurious', 1],
  ['timeouts', 'timeouts', 1],
  ['avg_recovery_s', 'avg recovery time (s)', 3],
  ['p95_rtt_ms', 'P95 RTT (ms)', 1],
  ['jain_fairness', 'Jain fairness', 3],
];

function Header({ algorithm, source }) {
  return (
    <th className="text-left font-normal py-2 px-2 align-bottom">
      <div className="flex items-center gap-1.5 text-slate-300">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: ALGORITHM_COLORS[algorithm] }} />
        {ALGORITHM_LABELS[algorithm]}
      </div>
      <div className="mt-1">
        <SourceBadge source={source} />
      </div>
    </th>
  );
}

/**
 * Mean (median, min-max, n) of every metric for one variant: the three
 * simulated algorithms (over seeds) and real Linux reno (over Mininet runs).
 */
export default function ResultsTable({ scenarioEntry, variantLabel }) {
  if (!scenarioEntry) {
    return (
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 text-xs text-slate-400 font-mono">
        No analysis for this scenario yet. Run <code>python -m tcp_lab.run_sim_scenarios</code> and{' '}
        <code>python -m tcp_lab.run_analysis</code>.
      </div>
    );
  }
  const item = scenarioEntry.variants.find((variant) => variant.label === variantLabel);
  if (!item) return null;

  const hasLinux = Boolean(item.mininet && item.mininet.linux_reno);
  const algorithms = SIM_ALGORITHMS.filter((algorithm) => item.simulator[algorithm]);
  const rows = METRICS.filter(([key]) => key !== 'jain_fairness' || item.num_flows > 1);

  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Table2 className="w-4 h-4 text-sky-400" />
        <h3 className="text-sm font-bold text-slate-100">
          {scenarioEntry.scenario} {variantLabel}: all runs
        </h3>
        <span className="text-[11px] font-mono text-slate-500">
          simulator: {item.seeds} seed(s) · mininet: {item.mininet_runs} run(s)
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-normal py-2 px-2 align-bottom">metric</th>
              {algorithms.map((algorithm) => (
                <Header key={algorithm} algorithm={algorithm} source="simulator" />
              ))}
              {hasLinux && <Header algorithm="linux_reno" source="mininet" />}
            </tr>
          </thead>
          <tbody className="text-slate-200">
            {rows.map(([key, label, digits]) => (
              <tr key={key} className="border-t border-slate-800">
                <td className="py-1.5 px-2 text-slate-400">{label}</td>
                {algorithms.map((algorithm) => (
                  <td key={algorithm} className="px-2">
                    {formatStats(item.simulator[algorithm][key], digits)}
                  </td>
                ))}
                {hasLinux && <td className="px-2">{formatStats(item.mininet.linux_reno[key], digits)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {item.score && (
        <p className="text-[11px] text-slate-400 font-mono">
          Score for this variant (simulator, clear wins only):{' '}
          {algorithms.map((algorithm) => `${ALGORITHM_LABELS[algorithm]} ${item.score.points[algorithm]}`).join(', ')}
        </p>
      )}
      <p className="text-[11px] text-slate-500 font-mono">
        Cells: mean (median, min-max, n). Linux has no Tahoe; Linux reno without SACK behaves like New Reno.
      </p>
    </div>
  );
}
