import React, { useEffect, useRef, useState } from 'react';
import { Play, Square, Radio } from 'lucide-react';
import CwndChart from './CwndChart';
import SourceBadge from './SourceBadge';
import { ALGORITHM_COLORS, ALGORITHM_LABELS, SIM_ALGORITHMS } from './tcpLabStyle';
import {
  connectWebSocket,
  fetchTcpLabTimeseries,
  startTcpLabReplay,
  startTcpLabSimulation,
  stopTcpLabRun,
} from '../../services/api';

const SPEEDS = [0.5, 1, 2, 5, 10];

function emptyBuffer() {
  // samples[flow][algorithm] = { cwnd: [{x, y}], ssthresh: [{x, y}] }; losses: [...]
  return { samples: {}, losses: [], latest: {} };
}

/**
 * Live cwnd view. The backend runs the simulator (or reads a recorded Mininet
 * run) and streams TCP_CWND_SAMPLE / TCP_LOSS_EVENT messages over /ws/events;
 * this component only collects them and draws them.
 */
export default function LivePanel({ scenario, variant, addLog }) {
  const [mode, setMode] = useState('simulate');           // 'simulate' | 'replay'
  const [algorithms, setAlgorithms] = useState(SIM_ALGORITHMS);
  const [seed, setSeed] = useState(1);
  const [speed, setSpeed] = useState(1);
  const [mininetRuns, setMininetRuns] = useState([]);
  const [replayRun, setReplayRun] = useState(1);
  const [run, setRun] = useState(null);                   // what the backend is playing
  const [state, setState] = useState('idle');             // idle | running | finished | stopped
  const [flow, setFlow] = useState(0);
  const [results, setResults] = useState(null);           // TCP_LAB_RUN_FINISHED numbers
  const [error, setError] = useState('');
  // What is drawn: a snapshot of the buffer, copied 5 times a second
  const [view, setView] = useState(emptyBuffer());

  // Messages are collected here (a ref: adding a sample must not re-render)
  const buffer = useRef(emptyBuffer());
  const runIdRef = useRef(null);

  const showBuffer = () => {
    const data = buffer.current;
    setView({ samples: data.samples, losses: [...data.losses], latest: { ...data.latest } });
  };

  // Which recorded Mininet runs exist for this variant (for the replay mode)
  useEffect(() => {
    let cancelled = false;
    if (!scenario || !variant) return undefined;
    fetchTcpLabTimeseries(scenario.id, variant.label)
      .then((data) => {
        if (cancelled) return;
        const runs = data && data.mininet_runs ? data.mininet_runs : [];
        setMininetRuns(runs);
        if (runs.length > 0) setReplayRun(runs[0]);
      })
      .catch(() => {
        if (!cancelled) setMininetRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, [scenario, variant]);

  // One WebSocket for the page; keep only messages of the run we started
  useEffect(() => {
    const ws = connectWebSocket((message) => {
      if (!message.type || !message.type.startsWith('TCP_')) return;
      if (message.run_id !== runIdRef.current) return;
      const data = buffer.current;
      if (message.type === 'TCP_CWND_SAMPLE') {
        const byFlow = data.samples[message.flow] || (data.samples[message.flow] = {});
        const line = byFlow[message.algorithm] || (byFlow[message.algorithm] = { cwnd: [], ssthresh: [] });
        line.cwnd.push({ x: message.time, y: message.cwnd });
        if (message.ssthresh !== null && message.ssthresh < 1e5) {
          line.ssthresh.push({ x: message.time, y: message.ssthresh });
        }
        data.latest[`${message.flow}/${message.algorithm}`] = message;
      } else if (message.type === 'TCP_LOSS_EVENT') {
        data.losses.push(message);
      } else if (message.type === 'TCP_LAB_RUN_FINISHED') {
        showBuffer();
        setState('finished');
        setResults(message.results);
      } else if (message.type === 'TCP_LAB_RUN_STOPPED') {
        showBuffer();
        setState('stopped');
      }
    });
    return () => {
      if (ws) ws.close();
    };
  }, []);

  // Redraw 5 times a second while running (not on every message)
  useEffect(() => {
    if (state !== 'running') return undefined;
    const timer = setInterval(showBuffer, 200);
    return () => clearInterval(timer);
  }, [state]);

  const start = async () => {
    setError('');
    setResults(null);
    setFlow(0);
    buffer.current = emptyBuffer();
    setView(emptyBuffer());
    try {
      const answer =
        mode === 'simulate'
          ? await startTcpLabSimulation({ scenario: scenario.id, variant: variant.label, algorithms, seed, speed })
          : await startTcpLabReplay({ scenario: scenario.id, variant: variant.label, run: replayRun, speed });
      runIdRef.current = answer.run_id;
      setRun(answer);
      setState('running');
      if (addLog) addLog(`TCP Lab: ${answer.mode} ${answer.scenario} ${answer.variant} started`, 'info');
    } catch (err) {
      setError(err.message);
    }
  };

  const stop = async () => {
    try {
      await stopTcpLabRun();
    } catch (err) {
      setError(err.message);
    }
  };

  const toggleAlgorithm = (algorithm) => {
    if (algorithms.includes(algorithm)) {
      if (algorithms.length > 1) setAlgorithms(algorithms.filter((a) => a !== algorithm));
    } else {
      setAlgorithms(SIM_ALGORITHMS.filter((a) => a === algorithm || algorithms.includes(a)));
    }
  };

  const flowSamples = view.samples[flow] || {};
  const flowLosses = view.losses.filter((loss) => loss.flow === flow);
  const numFlows = run ? run.num_flows : variant ? variant.num_flows : 1;
  const latest = Object.keys(view.latest)
    .filter((key) => key.startsWith(`${flow}/`))
    .map((key) => view.latest[key]);

  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-sky-400" />
          <h3 className="text-sm font-bold text-slate-100">Live congestion window</h3>
          {run && <SourceBadge source={run.source} />}
          {run && <span className="text-[11px] font-mono text-slate-500">#{run.run_id} · {state}</span>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={start}
            disabled={!variant || (mode === 'replay' && mininetRuns.length === 0)}
            className="px-3 py-1.5 rounded-xl text-xs font-bold bg-sky-500 text-slate-950 disabled:opacity-40 flex items-center gap-1.5"
          >
            <Play className="w-3.5 h-3.5" /> Start
          </button>
          <button
            onClick={stop}
            disabled={state !== 'running'}
            className="px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-900 text-slate-300 border border-slate-700 disabled:opacity-40 flex items-center gap-1.5"
          >
            <Square className="w-3.5 h-3.5" /> Stop
          </button>
        </div>
      </div>

      {/* Controls: one row */}
      <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-slate-300">
        <div className="flex rounded-xl overflow-hidden border border-slate-700">
          <button
            onClick={() => setMode('simulate')}
            className={`px-3 py-1.5 ${mode === 'simulate' ? 'bg-slate-700 text-slate-100' : 'bg-slate-900 text-slate-400'}`}
          >
            Simulator
          </button>
          <button
            onClick={() => setMode('replay')}
            className={`px-3 py-1.5 ${mode === 'replay' ? 'bg-slate-700 text-slate-100' : 'bg-slate-900 text-slate-400'}`}
          >
            Mininet replay
          </button>
        </div>

        {mode === 'simulate' ? (
          <>
            {SIM_ALGORITHMS.map((algorithm) => (
              <label key={algorithm} className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={algorithms.includes(algorithm)}
                  onChange={() => toggleAlgorithm(algorithm)}
                />
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: ALGORITHM_COLORS[algorithm] }} />
                {ALGORITHM_LABELS[algorithm]}
              </label>
            ))}
            <label className="flex items-center gap-1.5">
              seed
              <input
                type="number"
                min="1"
                max="1000"
                value={seed}
                onChange={(e) => setSeed(Math.max(1, Number(e.target.value) || 1))}
                className="w-16 bg-slate-900 border border-slate-700 rounded px-2 py-1"
              />
            </label>
          </>
        ) : (
          <label className="flex items-center gap-1.5">
            recorded run
            <select
              value={replayRun}
              onChange={(e) => setReplayRun(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1"
            >
              {mininetRuns.map((number) => (
                <option key={number} value={number}>
                  {number}
                </option>
              ))}
            </select>
            {mininetRuns.length === 0 && <span className="text-slate-500">no Mininet runs for this variant</span>}
          </label>
        )}

        <label className="flex items-center gap-1.5">
          speed
          <select
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1"
          >
            {SPEEDS.map((value) => (
              <option key={value} value={value}>
                {value}x
              </option>
            ))}
          </select>
        </label>

        {numFlows > 1 && (
          <label className="flex items-center gap-1.5">
            flow
            <select
              value={flow}
              onChange={(e) => setFlow(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1"
            >
              {Array.from({ length: numFlows }, (_, index) => (
                <option key={index} value={index}>
                  {index}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <p className="text-xs text-rose-300 font-mono">{error}</p>}

      <CwndChart series={flowSamples} losses={flowLosses} duration={run ? run.duration : variant?.duration} />

      <p className="text-[11px] text-slate-500 font-mono">
        Solid = cwnd, dashed = ssthresh, ▲ = fast retransmit, ✕ = timeout. Simulator runs are computed first and
        played back at the chosen speed; Mininet replay plays a recorded run of real Linux reno (SACK off) from its
        ss samples, which do not include the slow start / avoidance state.
      </p>

      {/* Latest value of each algorithm: a table, so nothing relies on colour */}
      {latest.length > 0 && (
        <table className="w-full text-xs font-mono">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-normal py-1">algorithm</th>
              <th className="text-right font-normal">time (s)</th>
              <th className="text-right font-normal">cwnd</th>
              <th className="text-right font-normal">ssthresh</th>
              <th className="text-right font-normal">state</th>
            </tr>
          </thead>
          <tbody className="text-slate-200">
            {latest.map((sample) => (
              <tr key={sample.algorithm} className="border-t border-slate-800">
                <td className="py-1 flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: ALGORITHM_COLORS[sample.algorithm] }} />
                  {ALGORITHM_LABELS[sample.algorithm]}
                </td>
                <td className="text-right">{sample.time.toFixed(2)}</td>
                <td className="text-right">{sample.cwnd.toFixed(1)}</td>
                <td className="text-right">
                  {sample.ssthresh === null || sample.ssthresh >= 1e5 ? '-' : sample.ssthresh.toFixed(1)}
                </td>
                <td className="text-right">{sample.state || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {results && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-bold text-slate-300">This run (seed {run?.seed})</h4>
            <SourceBadge source="simulator" />
          </div>
          <table className="w-full text-xs font-mono">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left font-normal py-1">algorithm</th>
                <th className="text-right font-normal">goodput (Mbit/s)</th>
                <th className="text-right font-normal">retransmissions</th>
                <th className="text-right font-normal">of which spurious</th>
                <th className="text-right font-normal">timeouts</th>
                <th className="text-right font-normal">avg recovery (s)</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {results.map((row) => (
                <tr key={row.algorithm} className="border-t border-slate-800">
                  <td className="py-1">{ALGORITHM_LABELS[row.algorithm]}</td>
                  <td className="text-right">{row.goodput_mbps.toFixed(2)}</td>
                  <td className="text-right">{row.retransmissions}</td>
                  <td className="text-right">{row.spurious_retransmissions}</td>
                  <td className="text-right">{row.timeouts}</td>
                  <td className="text-right">{row.avg_recovery_s === null ? '-' : row.avg_recovery_s.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-slate-500 font-mono">
            One seed only. For mean, median and spread over seeds and runs see the results table below.
          </p>
        </div>
      )}
    </div>
  );
}
