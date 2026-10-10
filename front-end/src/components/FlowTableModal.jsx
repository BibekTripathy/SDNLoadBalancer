import React from 'react';
import { X, ShieldCheck, HardDrive, Terminal } from 'lucide-react';

export default function FlowTableModal({ flowRules, onClose, activeAlgorithm }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden shadow-2xl flex flex-col">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 rounded-xl">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                OpenFlow 1.3 Flow Table Inspector
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Switch: s1 (DPID 0000000000000001) • Algorithm: {activeAlgorithm.toUpperCase()}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-100 bg-slate-800 hover:bg-slate-700 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content - Table of Flow Rules */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          <div className="overflow-x-auto border border-slate-800 rounded-xl">
            <table className="w-full text-left font-mono text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] border-b border-slate-800">
                <tr>
                  <th className="p-3">Priority</th>
                  <th className="p-3">Match Fields</th>
                  <th className="p-3">Instructions / Actions</th>
                  <th className="p-3">Purpose & Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                {flowRules.map((rule, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40 transition">
                    <td className="p-3 font-bold text-indigo-400">{rule.priority}</td>
                    <td className="p-3 font-bold text-sky-300">{rule.match}</td>
                    <td className="p-3 font-bold text-purple-300">{rule.actions}</td>
                    <td className="p-3 text-slate-400 font-sans text-xs">{rule.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs text-slate-400 flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>
              Flow rules installed via Ryu Controller <code className="text-sky-300">FlowManager</code> module over OpenFlow 1.3 protocol.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold transition"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
}
