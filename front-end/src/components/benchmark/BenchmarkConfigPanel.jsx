import React, { useState } from 'react';
import { Play, Settings2, ShieldAlert, Clock, Zap, Users, Repeat, Activity, AlertCircle } from 'lucide-react';

const ALL_ALGORITHMS = [
  { id: 'round_robin', name: 'Round Robin', color: 'sky' },
  { id: 'weighted_round_robin', name: 'Weighted Round Robin', color: 'indigo' },
  { id: 'least_connections', name: 'Least Connections', color: 'emerald' },
  { id: 'least_bandwidth', name: 'Least Bandwidth', color: 'purple' },
  { id: 'random', name: 'Random', color: 'pink' },
  { id: 'adaptive', name: 'Adaptive (AI/Composite)', color: 'amber' },
];

export default function BenchmarkConfigPanel({ onStart, isRunning }) {
  const [name, setName] = useState('SDN Load Balancing Experiment');
  const [selectedAlgorithms, setSelectedAlgorithms] = useState([
    'round_robin',
    'least_connections',
    'weighted_round_robin',
  ]);
  const [rate, setRate] = useState(25);
  const [concurrency, setConcurrency] = useState(4);
  const [duration, setDuration] = useState(8);
  const [warmupDuration, setWarmupDuration] = useState(2);
  const [repetitions, setRepetitions] = useState(1);
  const [enableLatencyInjection, setEnableLatencyInjection] = useState(false);
  const [injectedLatencyServer2, setInjectedLatencyServer2] = useState(30);
  const [enableFailureScenario, setEnableFailureScenario] = useState(false);
  const [failureServer, setFailureServer] = useState('server1');
  const [failureAtSecond, setFailureAtSecond] = useState(3);
  const [recoverAtSecond, setRecoverAtSecond] = useState(6);
  const [errorMsg, setErrorMsg] = useState('');

  const toggleAlgorithm = (algoId) => {
    if (selectedAlgorithms.includes(algoId)) {
      if (selectedAlgorithms.length === 1) {
        setErrorMsg('At least one algorithm must be selected.');
        return;
      }
      setSelectedAlgorithms(selectedAlgorithms.filter((id) => id !== algoId));
    } else {
      setSelectedAlgorithms([...selectedAlgorithms, algoId]);
    }
    setErrorMsg('');
  };

  const handleSelectAll = () => {
    setSelectedAlgorithms(ALL_ALGORITHMS.map((a) => a.id));
    setErrorMsg('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (selectedAlgorithms.length === 0) {
      setErrorMsg('Please select at least one algorithm.');
      return;
    }
    if (warmupDuration >= duration) {
      setErrorMsg('Warm-up duration must be strictly less than total duration.');
      return;
    }

    const config = {
      name: name || 'SDN Benchmark Run',
      algorithms: selectedAlgorithms,
      rate: Number(rate),
      concurrency: Number(concurrency),
      duration: Number(duration),
      warmup_duration: Number(warmupDuration),
      repetitions: Number(repetitions),
      inject_latency_ms: enableLatencyInjection ? { server2: Number(injectedLatencyServer2) } : null,
      failure_scenario: enableFailureScenario
        ? {
            server_id: failureServer,
            at_second: Number(failureAtSecond),
            recover_at_second: Number(recoverAtSecond),
          }
        : null,
    };

    setErrorMsg('');
    onStart(config);
  };

  const totalEstimatedSeconds = selectedAlgorithms.length * repetitions * duration;

  return (
    <form onSubmit={handleSubmit} className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Settings2 className="w-5 h-5 text-sky-400" />
          <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
            Experiment Configuration Panel
          </h2>
        </div>
        <div className="text-xs font-mono text-slate-400 bg-slate-900 px-3 py-1 rounded-lg border border-slate-800">
          Est. Execution Time:{' '}
          <span className="text-amber-400 font-bold">{totalEstimatedSeconds}s</span>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Experiment Name */}
      <div>
        <label className="block text-xs font-mono text-slate-400 mb-1">Experiment Label</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isRunning}
          className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-500 transition"
          placeholder="e.g. High Concurrency Comparison"
        />
      </div>

      {/* Algorithm Multi-Selector */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Algorithms to Benchmark ({selectedAlgorithms.length} selected)
          </label>
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <button
              type="button"
              onClick={handleSelectAll}
              disabled={isRunning}
              className="text-sky-400 hover:text-sky-300 transition"
            >
              Select All
            </button>
            <span className="text-slate-600">|</span>
            <button
              type="button"
              onClick={() => setSelectedAlgorithms(['round_robin'])}
              disabled={isRunning}
              className="text-slate-400 hover:text-slate-200 transition"
            >
              Reset Default
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {ALL_ALGORITHMS.map((algo) => {
            const isSelected = selectedAlgorithms.includes(algo.id);
            return (
              <button
                key={algo.id}
                type="button"
                onClick={() => toggleAlgorithm(algo.id)}
                disabled={isRunning}
                className={`px-3 py-2.5 rounded-xl text-xs font-medium border text-left transition flex items-center justify-between ${
                  isSelected
                    ? 'bg-sky-500/15 border-sky-500/50 text-sky-200 shadow-sm shadow-sky-500/10'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>{algo.name}</span>
                <span
                  className={`w-2 h-2 rounded-full ${
                    isSelected ? 'bg-sky-400 animate-pulse' : 'bg-slate-700'
                  }`}
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* Numerical Sliders Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {/* Rate (RPS) */}
        <div className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <span className="text-slate-400 flex items-center gap-1">
              <Activity className="w-3.5 h-3.5 text-sky-400" />
              Target Rate
            </span>
            <span className="text-sky-400 font-bold">{rate} req/s</span>
          </div>
          <input
            type="range"
            min="5"
            max="150"
            step="5"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            disabled={isRunning}
            className="w-full accent-sky-400"
          />
        </div>

        {/* Concurrency */}
        <div className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <span className="text-slate-400 flex items-center gap-1">
              <Users className="w-3.5 h-3.5 text-indigo-400" />
              Concurrency
            </span>
            <span className="text-indigo-400 font-bold">{concurrency} clients</span>
          </div>
          <input
            type="range"
            min="1"
            max="20"
            step="1"
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value)}
            disabled={isRunning}
            className="w-full accent-indigo-400"
          />
        </div>

        {/* Duration */}
        <div className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <span className="text-slate-400 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-emerald-400" />
              Duration
            </span>
            <span className="text-emerald-400 font-bold">{duration}s</span>
          </div>
          <input
            type="range"
            min="4"
            max="30"
            step="2"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            disabled={isRunning}
            className="w-full accent-emerald-400"
          />
        </div>

        {/* Warm-up Duration */}
        <div className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <span className="text-slate-400 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              Warm-up
            </span>
            <span className="text-amber-400 font-bold">{warmupDuration}s</span>
          </div>
          <input
            type="range"
            min="0"
            max={Math.max(1, duration - 2)}
            step="1"
            value={warmupDuration}
            onChange={(e) => setWarmupDuration(e.target.value)}
            disabled={isRunning}
            className="w-full accent-amber-400"
          />
        </div>

        {/* Repetitions */}
        <div className="bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <span className="text-slate-400 flex items-center gap-1">
              <Repeat className="w-3.5 h-3.5 text-purple-400" />
              Repetitions
            </span>
            <span className="text-purple-400 font-bold">{repetitions}x</span>
          </div>
          <input
            type="range"
            min="1"
            max="3"
            step="1"
            value={repetitions}
            onChange={(e) => setRepetitions(e.target.value)}
            disabled={isRunning}
            className="w-full accent-purple-400"
          />
        </div>
      </div>

      {/* Advanced Injections Accordion / Toggles */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
        {/* Latency Injection */}
        <div className="bg-slate-900/50 p-3.5 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              Simulate Server Asymmetry
            </label>
            <input
              type="checkbox"
              checked={enableLatencyInjection}
              onChange={(e) => setEnableLatencyInjection(e.target.checked)}
              disabled={isRunning}
              className="accent-amber-400 rounded cursor-pointer"
            />
          </div>
          <p className="text-[11px] text-slate-500 mb-2">
            Inject synthetic processing latency into Server 2 to evaluate adaptive responsiveness.
          </p>
          {enableLatencyInjection && (
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-slate-400">Server 2 Extra Delay:</span>
              <input
                type="number"
                min="5"
                max="100"
                value={injectedLatencyServer2}
                onChange={(e) => setInjectedLatencyServer2(e.target.value)}
                disabled={isRunning}
                className="w-20 bg-slate-950 border border-slate-700 px-2 py-1 rounded text-amber-300"
              />
              <span className="text-slate-500">ms</span>
            </div>
          )}
        </div>

        {/* Backend Failure & Recovery */}
        <div className="bg-slate-900/50 p-3.5 rounded-xl border border-slate-800/80">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              Fault Injection & Recovery Scenario
            </label>
            <input
              type="checkbox"
              checked={enableFailureScenario}
              onChange={(e) => setEnableFailureScenario(e.target.checked)}
              disabled={isRunning}
              className="accent-rose-400 rounded cursor-pointer"
            />
          </div>
          <p className="text-[11px] text-slate-500 mb-2">
            Simulate a temporary node crash to measure algorithm failover and recovery latency.
          </p>
          {enableFailureScenario && (
            <div className="grid grid-cols-3 gap-2 text-xs font-mono">
              <div>
                <span className="text-[10px] text-slate-400 block mb-0.5">Target</span>
                <select
                  value={failureServer}
                  onChange={(e) => setFailureServer(e.target.value)}
                  disabled={isRunning}
                  className="w-full bg-slate-950 border border-slate-700 p-1 rounded text-rose-300 text-xs"
                >
                  <option value="server1">server1</option>
                  <option value="server2">server2</option>
                  <option value="server3">server3</option>
                </select>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block mb-0.5">Fail At</span>
                <input
                  type="number"
                  min="1"
                  max={duration - 2}
                  value={failureAtSecond}
                  onChange={(e) => setFailureAtSecond(e.target.value)}
                  disabled={isRunning}
                  className="w-full bg-slate-950 border border-slate-700 p-1 rounded text-rose-300 text-xs"
                />
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block mb-0.5">Recover At</span>
                <input
                  type="number"
                  min="2"
                  max={duration - 1}
                  value={recoverAtSecond}
                  onChange={(e) => setRecoverAtSecond(e.target.value)}
                  disabled={isRunning}
                  className="w-full bg-slate-950 border border-slate-700 p-1 rounded text-emerald-300 text-xs"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Start Button */}
      <div className="pt-2 flex justify-end">
        <button
          type="submit"
          disabled={isRunning}
          className={`px-6 py-2.5 rounded-xl font-bold text-xs uppercase tracking-wider flex items-center gap-2 shadow-lg transition ${
            isRunning
              ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
              : 'bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-slate-950 shadow-sky-500/20 active:scale-95'
          }`}
        >
          <Play className="w-4 h-4 fill-current" />
          {isRunning ? 'Benchmark Running...' : 'Execute Benchmark Experiment'}
        </button>
      </div>
    </form>
  );
}
