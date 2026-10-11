import React, { useState, useEffect } from 'react';
import { X, Server, Plus, AlertCircle, RefreshCw, Sparkles, Check } from 'lucide-react';
import { fetchServerSuggest } from '../services/api';

export default function AddServerModal({
  isOpen,
  onClose,
  onAddServer,
  existingServers = [],
  simulationMode = false,
}) {
  const [serverId, setServerId] = useState('');
  const [ip, setIp] = useState('');
  const [port, setPort] = useState(80);
  const [switchPort, setSwitchPort] = useState(5);
  const [weight, setWeight] = useState(1);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingSuggestion, setIsFetchingSuggestion] = useState(false);

  // Auto-load suggestions whenever modal opens
  useEffect(() => {
    if (isOpen) {
      loadSuggestions();
    }
  }, [isOpen]);

  const loadSuggestions = async () => {
    setIsFetchingSuggestion(true);
    setError('');
    try {
      if (!simulationMode) {
        const suggest = await fetchServerSuggest();
        if (suggest) {
          setServerId(suggest.id || '');
          setIp(suggest.ip || '');
          setPort(suggest.port || 80);
          setSwitchPort(suggest.switch_port || 5);
          setWeight(suggest.weight || 1);
          setIsFetchingSuggestion(false);
          return;
        }
      }
    } catch {
      // Fallback local suggestion
    }

    // Local client-side suggestion based on existingServers
    const existingIds = new Set(existingServers.map((s) => s.id || s.server_id));
    const existingIps = new Set(existingServers.map((s) => s.ip));
    const existingPorts = new Set(existingServers.map((s) => s.switch_port));

    let idx = 1;
    while (existingIds.has(`server${idx}`)) idx++;
    setServerId(`server${idx}`);

    let ipIdx = 2;
    while (existingIps.has(`10.0.0.${ipIdx}`) || ipIdx === 100) ipIdx++;
    setIp(`10.0.0.${ipIdx}`);

    let swPort = 2;
    while (existingPorts.has(swPort)) swPort++;
    setSwitchPort(swPort);

    setPort(80);
    setWeight(1);
    setIsFetchingSuggestion(false);
  };

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    const cleanId = serverId.trim();
    const cleanIp = ip.trim();
    const numPort = parseInt(port, 10);
    const numSwitchPort = parseInt(switchPort, 10);
    const numWeight = parseInt(weight, 10);

    if (!cleanId) {
      setError('Server ID is required');
      return;
    }

    if (!cleanIp) {
      setError('IP address is required');
      return;
    }

    if (existingServers.some((s) => (s.id || s.server_id) === cleanId)) {
      setError(`Server ID "${cleanId}" already exists in pool`);
      return;
    }

    if (existingServers.some((s) => s.ip === cleanIp)) {
      setError(`IP address "${cleanIp}" is already assigned to another backend`);
      return;
    }

    if (cleanIp === '10.0.0.1' || cleanIp === '10.0.0.100') {
      setError(`IP "${cleanIp}" is reserved for Client or Virtual IP (10.0.0.100)`);
      return;
    }

    if (numSwitchPort === 1) {
      setError('Switch port 1 is reserved for the Client (h1)');
      return;
    }

    if (existingServers.some((s) => s.switch_port === numSwitchPort)) {
      setError(`Switch port ${numSwitchPort} is already connected to another backend`);
      return;
    }

    setIsLoading(true);
    try {
      await onAddServer({
        id: cleanId,
        server_id: cleanId,
        ip: cleanIp,
        port: numPort,
        switch_port: numSwitchPort,
        weight: numWeight,
        status: 'HEALTHY',
      });
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to add backend server');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl flex flex-col">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-sky-500/10 text-sky-400 border border-sky-500/30">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-100">Add Backend Server</h3>
              <p className="text-xs text-slate-400 font-mono">
                Connect and register a new host to OVS Switch
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

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs font-mono">
          {error && (
            <div className="p-3 bg-red-950/60 border border-red-800/80 rounded-xl text-red-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-400 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Quick Auto-Suggest Bar */}
          <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-xl border border-slate-800">
            <div className="flex items-center gap-2 text-slate-400 text-[11px]">
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Collision-Free Defaults</span>
            </div>
            <button
              type="button"
              onClick={loadSuggestions}
              disabled={isFetchingSuggestion}
              className="text-[11px] text-sky-400 hover:text-sky-300 flex items-center gap-1 font-semibold transition"
            >
              <RefreshCw className={`w-3 h-3 ${isFetchingSuggestion ? 'animate-spin' : ''}`} />
              Auto-Suggest
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-400 text-[11px] mb-1">SERVER ID</label>
              <input
                type="text"
                value={serverId}
                onChange={(e) => setServerId(e.target.value)}
                placeholder="server4"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">IP ADDRESS</label>
              <input
                type="text"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="10.0.0.5"
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-slate-400 text-[11px] mb-1">HTTP PORT</label>
              <input
                type="number"
                min="1"
                max="65535"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">SWITCH PORT</label>
              <input
                type="number"
                min="2"
                max="254"
                value={switchPort}
                onChange={(e) => setSwitchPort(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">WEIGHT</label>
              <input
                type="number"
                min="1"
                max="100"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>
          </div>

          <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800 text-[11px] text-slate-400 font-sans">
            {simulationMode ? (
              <span className="text-amber-400/90 flex items-center gap-1.5 font-mono text-[10px]">
                ⚡ Simulation Demo Mode: backend will be simulated with synthetic metrics.
              </span>
            ) : (
              <span className="text-sky-400/90 flex items-center gap-1.5 font-mono text-[10px]">
                🌐 Live Mode: backend will register with Ryu Controller & OpenFlow rules.
              </span>
            )}
          </div>

          {/* Modal Actions */}
          <div className="pt-3 border-t border-slate-800 flex justify-end gap-2.5">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-sky-500/20 active:scale-95 disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" />
                  Add Server
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
