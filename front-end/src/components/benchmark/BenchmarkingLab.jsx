import React, { useState, useEffect, useCallback } from 'react';
import {
  FlaskConical,
  Download,
  FileSpreadsheet,
  FileCode,
  History,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import BenchmarkConfigPanel from './BenchmarkConfigPanel';
import BenchmarkLiveStatus from './BenchmarkLiveStatus';
import AlgorithmComparisonTable from './AlgorithmComparisonTable';
import BenchmarkCharts from './BenchmarkCharts';
import BenchmarkHistoryModal from './BenchmarkHistoryModal';
import {
  startBenchmark,
  fetchBenchmarks,
  fetchActiveBenchmark,
  fetchBenchmarkDetails,
  cancelBenchmark,
  deleteBenchmark,
  getBenchmarkCsvUrl,
  getBenchmarkJsonUrl,
} from '../../services/api';

export default function BenchmarkingLab({ addLog }) {
  const [activeBenchmark, setActiveBenchmark] = useState(null);
  const [historyList, setHistoryList] = useState([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Load initial active benchmark and historical list
  const refreshHistory = useCallback(async () => {
    try {
      const list = await fetchBenchmarks();
      setHistoryList(list || []);
    } catch (err) {
      console.warn('Failed to fetch benchmark history:', err);
    }
  }, []);

  const refreshActive = useCallback(async () => {
    try {
      const active = await fetchActiveBenchmark();
      if (active) {
        setActiveBenchmark(active);
      }
    } catch (err) {
      console.warn('Failed to fetch active benchmark:', err);
    }
  }, []);

  useEffect(() => {
    refreshHistory();
    refreshActive();
  }, [refreshHistory, refreshActive]);

  // Periodic polling while active benchmark is in progress
  useEffect(() => {
    if (!activeBenchmark || (activeBenchmark.status !== 'running' && activeBenchmark.status !== 'preparing')) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const details = await fetchBenchmarkDetails(activeBenchmark.id);
        setActiveBenchmark(details);
        if (details.status === 'completed' || details.status === 'failed' || details.status === 'cancelled') {
          refreshHistory();
          if (addLog) {
            addLog(`Benchmark #${details.id} reached state: ${details.status.toUpperCase()}`, 'info');
          }
        }
      } catch (err) {
        console.error('Polling error for benchmark:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeBenchmark, refreshHistory, addLog]);

  const handleStartBenchmark = async (config) => {
    setErrorMsg('');
    setIsLoading(true);
    try {
      const newBenchmark = await startBenchmark(config);
      setActiveBenchmark(newBenchmark);
      if (addLog) {
        addLog(`Started Benchmark #${newBenchmark.id} with ${config.algorithms.length} algorithms`, 'success');
      }
      refreshHistory();
    } catch (err) {
      setErrorMsg(err.message || 'Failed to start benchmark experiment');
      if (addLog) {
        addLog(`Benchmark start failed: ${err.message}`, 'error');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelBenchmark = async (benchmarkId) => {
    try {
      await cancelBenchmark(benchmarkId);
      const updated = await fetchBenchmarkDetails(benchmarkId);
      setActiveBenchmark(updated);
      if (addLog) {
        addLog(`Benchmark #${benchmarkId} cancelled safely`, 'warning');
      }
      refreshHistory();
    } catch (err) {
      setErrorMsg(err.message || 'Failed to cancel benchmark');
    }
  };

  const handleSelectHistoricalRun = async (benchmarkId) => {
    setIsLoading(true);
    try {
      const details = await fetchBenchmarkDetails(benchmarkId);
      setActiveBenchmark(details);
    } catch (err) {
      setErrorMsg(`Failed to load benchmark #${benchmarkId}: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteRun = async (benchmarkId) => {
    try {
      await deleteBenchmark(benchmarkId);
      if (activeBenchmark?.id === benchmarkId) {
        setActiveBenchmark(null);
      }
      refreshHistory();
    } catch (err) {
      setErrorMsg(`Failed to delete benchmark: ${err.message}`);
    }
  };

  const isRunning = activeBenchmark?.status === 'running' || activeBenchmark?.status === 'preparing';

  return (
    <div className="space-y-6">
      {/* Top Banner & Control Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-gradient-to-br from-sky-500/20 to-indigo-500/20 text-sky-400 rounded-xl border border-sky-500/30 shadow-md">
              <FlaskConical className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                SDN Benchmarking Laboratory
              </h2>
              <p className="text-xs text-slate-400">
                Rigorous multi-algorithm experimental evaluation under reproducible network workloads.
              </p>
            </div>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex items-center gap-2 font-mono text-xs">
          {/* History Button */}
          <button
            type="button"
            onClick={() => setShowHistoryModal(true)}
            className="px-3 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-xl flex items-center gap-1.5 transition shadow-sm"
          >
            <History className="w-3.5 h-3.5 text-indigo-400" />
            <span>Past Runs</span>
            {historyList.length > 0 && (
              <span className="bg-slate-800 text-slate-400 text-[10px] px-1.5 py-0.2 rounded-full ml-1">
                {historyList.length}
              </span>
            )}
          </button>

          {/* Export CSV */}
          {activeBenchmark && (
            <a
              href={getBenchmarkCsvUrl(activeBenchmark.id)}
              download={`benchmark-${activeBenchmark.id}.csv`}
              className="px-3 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-xl flex items-center gap-1.5 transition shadow-sm"
              title="Export Tabular Results to CSV"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
              <span>CSV</span>
            </a>
          )}

          {/* Export JSON */}
          {activeBenchmark && (
            <a
              href={getBenchmarkJsonUrl(activeBenchmark.id)}
              download={`benchmark-${activeBenchmark.id}.json`}
              className="px-3 py-2 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-xl flex items-center gap-1.5 transition shadow-sm"
              title="Export Complete Run Details to JSON"
            >
              <FileCode className="w-3.5 h-3.5 text-sky-400" />
              <span>JSON</span>
            </a>
          )}
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-xl text-xs flex items-center gap-2 font-mono">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 1. Experiment Configuration Panel */}
      <BenchmarkConfigPanel onStart={handleStartBenchmark} isRunning={isRunning || isLoading} />

      {/* 2. Live Execution Status Banner */}
      {activeBenchmark && (
        <BenchmarkLiveStatus benchmark={activeBenchmark} onCancel={handleCancelBenchmark} />
      )}

      {/* 3. Performance Comparison Table */}
      {activeBenchmark && activeBenchmark.summary && activeBenchmark.summary.length > 0 && (
        <AlgorithmComparisonTable
          summary={activeBenchmark.summary}
          runs={activeBenchmark.runs}
          isSimulated={activeBenchmark.is_simulated}
        />
      )}

      {/* 4. Comparative Charts */}
      {activeBenchmark && activeBenchmark.summary && activeBenchmark.summary.length > 0 && (
        <BenchmarkCharts summary={activeBenchmark.summary} runs={activeBenchmark.runs} />
      )}

      {/* History Modal Drawer */}
      <BenchmarkHistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        historyList={historyList}
        onSelectRun={handleSelectHistoricalRun}
        onDeleteRun={handleDeleteRun}
      />
    </div>
  );
}
