import React, { useEffect, useState } from 'react';
import { Gauge, Info, RefreshCw } from 'lucide-react';
import LivePanel from './LivePanel';
import ResultsTable from './ResultsTable';
import AnalysisPanel from './AnalysisPanel';
import SourceBadge from './SourceBadge';
import { fetchTcpLabAnalysis, fetchTcpLabScenarios } from '../../services/api';

/**
 * TCP Congestion Control Lab page: Tahoe, Reno and New Reno.
 * Everything shown comes from /api/tcp-lab; this page has no TCP logic.
 */
export default function TcpLab({ addLog }) {
  const [scenarios, setScenarios] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [scenarioId, setScenarioId] = useState('S2');
  const [variantLabel, setVariantLabel] = useState('');
  const [error, setError] = useState('');

  // Ask the backend for the scenario list and the Phase 5 analysis
  const fetchAll = () => Promise.all([fetchTcpLabScenarios(), fetchTcpLabAnalysis()]);

  const show = ([scenarioList, analysisData]) => {
    setScenarios(scenarioList || []);
    setAnalysis(analysisData);
    setError('');
  };

  const showError = (err) => setError(`${err.message}. Is the FastAPI backend running?`);

  // Load once when the page opens (ignore the answer if the page was closed)
  useEffect(() => {
    let closed = false;
    fetchAll()
      .then((data) => {
        if (!closed) show(data);
      })
      .catch((err) => {
        if (!closed) showError(err);
      });
    return () => {
      closed = true;
    };
  }, []);

  const load = () => fetchAll().then(show).catch(showError);

  const scenario = scenarios.find((item) => item.id === scenarioId);
  const variant = scenario ? scenario.variants.find((item) => item.label === variantLabel) || scenario.variants[0] : null;

  return (
    <div className="space-y-6">
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-slate-900 border border-slate-800 rounded-xl text-sky-400">
              <Gauge className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100">TCP Congestion Control Lab</h2>
              <p className="text-xs text-slate-400">Tahoe, Reno and New Reno under loss, load, bandwidth and delay changes</p>
            </div>
          </div>
          <button
            onClick={load}
            className="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 text-slate-300 border border-slate-700 flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Reload results
          </button>
        </div>
        <div className="flex items-start gap-2 text-[11px] text-slate-400 font-mono">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <p>
            <SourceBadge source="simulator" /> Python model of all three algorithms.{' '}
            <SourceBadge source="mininet" /> real Linux reno with SACK off, which behaves like New Reno; Linux has no
            Tahoe, so the three-way comparison comes from the simulator and Mininet checks it.
          </p>
        </div>

        {/* Scenario and variant: shared by every panel below */}
        <div className="flex flex-wrap items-end gap-4 text-xs font-mono text-slate-300">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-sans font-semibold text-slate-400">Scenario</span>
            <select
              value={scenarioId}
              onChange={(e) => {
                setScenarioId(e.target.value);
                setVariantLabel('');
              }}
              className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5"
            >
              {scenarios.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} {item.name}
                </option>
              ))}
            </select>
          </label>
          {scenario && (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-sans font-semibold text-slate-400">Variant</span>
              <select
                value={variant ? variant.label : ''}
                onChange={(e) => setVariantLabel(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5"
              >
                {scenario.variants.map((item) => (
                  <option key={item.label} value={item.label}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {variant && (
          <p className="text-xs font-mono text-slate-500">
            {variant.bandwidth_mbps} Mbit/s · one-way delay {variant.delay_ms} ms · queue {variant.queue_size} ·
            loss {(variant.loss_rate * 100).toFixed(1)} % · {variant.num_flows} flow(s) · {variant.duration} s
          </p>
        )}
        {scenario && <p className="text-xs text-slate-400">{scenario.description}</p>}
        {error && <p className="text-xs text-rose-300 font-mono">{error}</p>}
      </div>

      {scenario && variant && <LivePanel scenario={scenario} variant={variant} addLog={addLog} />}

      {scenario && variant && (
        <ResultsTable
          scenarioEntry={analysis ? analysis.scenarios[scenario.id] : null}
          variantLabel={variant.label}
        />
      )}

      <AnalysisPanel analysis={analysis} scenarioId={analysis && analysis.scenarios[scenarioId] ? scenarioId : null} />
    </div>
  );
}
