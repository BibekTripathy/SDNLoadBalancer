import React from 'react';
import { History, X, Trash2, ArrowRight, Clock, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export default function BenchmarkHistoryModal({
  isOpen,
  onClose,
  historyList = [],
  onSelectRun,
  onDeleteRun,
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-[#0D1322] border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg border border-indigo-500/20">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100">Historical Benchmark Runs</h3>
              <p className="text-[11px] text-slate-400">
                Persistent SQLite records. Click any run to inspect performance comparisons.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* List of Runs */}
        <div className="p-4 overflow-y-auto flex-1 divide-y divide-slate-800/60 space-y-2">
          {historyList.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs font-mono">
              No previous benchmark runs saved yet.
            </div>
          ) : (
            historyList.map((item) => {
              const formattedDate = new Date(item.created_at).toLocaleString();
              return (
                <div
                  key={item.id}
                  className="pt-2 first:pt-0 flex items-center justify-between gap-3 p-3 rounded-xl hover:bg-slate-900/60 transition group border border-transparent hover:border-slate-800"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-200">{item.name}</span>
                      <span className="text-[10px] font-mono text-slate-500">#{item.id}</span>
                      {item.is_simulated ? (
                        <span className="text-[9px] bg-amber-500/10 text-amber-400 border border-amber-500/30 px-1.5 py-0.2 rounded font-mono">
                          Simulated
                        </span>
                      ) : (
                        <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-1.5 py-0.2 rounded font-mono">
                          Mininet
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-400">
                      <span>{formattedDate}</span>
                      <span>•</span>
                      <span>{item.algorithms.join(', ')}</span>
                      <span>•</span>
                      <span>{item.total_runs} runs</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => {
                        onSelectRun(item.id);
                        onClose();
                      }}
                      className="px-3 py-1.5 bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/30 rounded-lg text-xs font-mono flex items-center gap-1.5 transition"
                    >
                      <span>Load</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => onDeleteRun(item.id)}
                      title="Delete Run"
                      className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
