import React, { useEffect, useState } from 'react';
import { Award, CheckSquare } from 'lucide-react';
import SourceBadge from './SourceBadge';
import { ALGORITHM_LABELS, formatStats } from './tcpLabStyle';
import { fetchTcpLabPlot } from '../../services/api';

/**
 * A plot PNG from the backend. Fetched with the API client (an <img src> to the
 * backend could not send the ngrok header) and shown from a blob: URL.
 */
function PlotImage({ name, alt, className }) {
  const [plot, setPlot] = useState({ name: null, url: null, failed: false });

  useEffect(() => {
    let closed = false;
    let url = null;
    fetchTcpLabPlot(name)
      .then((blobUrl) => {
        url = blobUrl;
        if (closed) URL.revokeObjectURL(blobUrl);
        else setPlot({ name, url: blobUrl, failed: false });
      })
      .catch(() => {
        if (!closed) setPlot({ name, url: null, failed: true });
      });
    return () => {
      closed = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [name]);

  // Until the new plot arrives, show nothing rather than the previous scenario's plot
  if (plot.name !== name) return null;
  if (plot.failed) return <p className="text-xs text-slate-500 font-mono">Plot {name} is not available.</p>;
  return <img src={plot.url} alt={alt} className={className} />;
}

function number(value, digits = 2) {
  return value === null || value === undefined ? '-' : Number(value).toFixed(digits);
}

/**
 * The Phase 5 conclusions, exactly as analysis.json states them:
 * the recommendation (simulator), the simulator-vs-Linux check, and the plots.
 */
export default function AnalysisPanel({ analysis, scenarioId }) {
  if (!analysis) return null;
  const recommendation = analysis.recommendation;
  const ranking = Object.entries(recommendation.overall_points).sort((a, b) => b[1] - a[1]);

  const checks = [];
  for (const id of Object.keys(analysis.scenarios)) {
    for (const item of analysis.scenarios[id].variants) {
      if (item.validation && item.validation.closer_by_goodput) {
        checks.push({ id, label: item.label, check: item.validation });
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
        <div className="flex items-center gap-2">
          <Award className="w-4 h-4 text-sky-400" />
          <h3 className="text-sm font-bold text-slate-100">Recommendation</h3>
          <SourceBadge source="simulator" />
        </div>
        <p className="text-sm text-slate-200">
          Recommended:{' '}
          <strong>{recommendation.winners.map((algorithm) => ALGORITHM_LABELS[algorithm]).join(' and ')}</strong>
        </p>
        <table className="text-xs font-mono">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-normal pr-10 py-1">algorithm</th>
              <th className="text-right font-normal pr-10">points</th>
              <th className="text-right font-normal">scenarios won</th>
            </tr>
          </thead>
          <tbody className="text-slate-200">
            {ranking.map(([algorithm, points]) => (
              <tr key={algorithm} className="border-t border-slate-800">
                <td className="pr-10 py-1">{ALGORITHM_LABELS[algorithm]}</td>
                <td className="text-right pr-10">{points}</td>
                <td className="text-right">{recommendation.scenarios_won[algorithm] || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-slate-500 font-mono">
          Points only for a clear win: the mean over seeds must beat the other by more than the standard deviation
          and by at least 2 %. Linux has no Tahoe, so only the simulator can rank the three.
        </p>
      </div>

      {checks.length > 0 && (
        <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
          <div className="flex items-center gap-2">
            <CheckSquare className="w-4 h-4 text-sky-400" />
            <h3 className="text-sm font-bold text-slate-100">Does the simulator match real Linux?</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left font-normal py-2 pr-10">variant</th>
                  <th className="text-left font-normal pr-10">
                    goodput: Linux reno <SourceBadge source="mininet" />
                  </th>
                  <th className="text-right font-normal pr-10">
                    New Reno, Linux-like start <SourceBadge source="simulator" />
                  </th>
                  <th className="text-right font-normal pr-10">
                    Reno, Linux-like start <SourceBadge source="simulator" />
                  </th>
                  <th className="text-left font-normal pr-10">closer by goodput</th>
                  <th className="text-left font-normal">Linux timeouts</th>
                </tr>
              </thead>
              <tbody className="text-slate-200">
                {checks.map(({ id, label, check }) => (
                  <tr key={`${id}-${label}`} className="border-t border-slate-800">
                    <td className="py-2 pr-10">
                      {id} {label}
                    </td>
                    <td className="pr-3">{formatStats(check.mininet_goodput)}</td>
                    <td className="text-right pr-10">{number(check.newreno_linux_start_goodput)}</td>
                    <td className="text-right pr-10">{number(check.reno_linux_start_goodput)}</td>
                    <td className="pr-3">{ALGORITHM_LABELS[check.closer_by_goodput]}</td>
                    <td>
                      {number(check.mininet_timeouts, 1)} ({check.timeouts_vs_simulator} simulated)
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-500 font-mono">
            Linux starts with no ssthresh limit, so it is compared with simulator runs that start the same way. Full
            explanation in results/analysis/report.md.
          </p>
        </div>
      )}

      {scenarioId && (
        <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
          <h3 className="text-sm font-bold text-slate-100">Analysis plots</h3>
          <PlotImage
            name={`${scenarioId}_comparison.png`}
            alt={`${scenarioId}: goodput, retransmissions, timeouts and recovery time for every algorithm`}
            className="w-full rounded-xl bg-white"
          />
          {(scenarioId === 'S6' || scenarioId === 'S6Q') && (
            <PlotImage
              name="s6_goodput_vs_rtt.png"
              alt="S6: goodput against RTT with the Mathis formula"
              className="w-full max-w-3xl rounded-xl bg-white"
            />
          )}
        </div>
      )}
    </div>
  );
}
