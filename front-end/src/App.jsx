import React, { useState } from 'react';
import { useSDNData } from './hooks/useSDNData';
import Header from './components/Header';
import TopologyCanvas from './components/TopologyCanvas';
import AlgorithmSelector from './components/AlgorithmSelector';
import SimulationPanel from './components/SimulationPanel';
import FlowTableModal from './components/FlowTableModal';
import ServerDetailModal from './components/ServerDetailModal';
import AddServerModal from './components/AddServerModal';
import BenchmarkingLab from './components/benchmark/BenchmarkingLab';
import TcpLab from './components/tcplab/TcpLab';
import { Network, FlaskConical, Gauge } from 'lucide-react';

export default function App() {
  const {
    isLiveConnected,
    simulationMode,
    setSimulationMode,
    activeAlgorithm,
    algorithms,
    servers,
    currentMetrics,
    trafficRate,
    setTrafficRate,
    trafficLogs,
    flowRules,
    lastSelectedServer,
    switchAlgorithm,
    toggleServerHealth,
    addServer,
    removeServer,
    drainServer,
    updateServerWeight,
    triggerSingleRequest,
    addLog,
  } = useSDNData();

  const [activeTab, setActiveTab] = useState('topology'); // 'topology' | 'benchmark' | 'tcplab'
  const [showFlowModal, setShowFlowModal] = useState(false);
  const [showAddServerModal, setShowAddServerModal] = useState(false);
  const [selectedServerModal, setSelectedServerModal] = useState(null);

  return (
    <div className="min-h-screen text-slate-100 flex flex-col font-sans">
      {/* Navigation & Header */}
      <Header
        isLiveConnected={isLiveConnected}
        simulationMode={simulationMode}
        setSimulationMode={setSimulationMode}
      />

      {/* Primary Dashboard Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('topology')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                activeTab === 'topology'
                  ? 'bg-sky-500 text-slate-950 shadow-lg shadow-sky-500/20'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <Network className="w-4 h-4" />
              SDN Topology & Controller
            </button>


            <button
              onClick={() => setActiveTab('benchmark')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                activeTab === 'benchmark'
                  ? 'bg-sky-500 text-slate-950 shadow-lg shadow-sky-500/20'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <FlaskConical className="w-4 h-4" />
              Benchmarking Lab
            </button>

            <button
              onClick={() => setActiveTab('tcplab')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                activeTab === 'tcplab'
                  ? 'bg-sky-500 text-slate-950 shadow-lg shadow-sky-500/20'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <Gauge className="w-4 h-4" />
              TCP Lab
            </button>
          </div>
        </div>

        {/* Tab 1: Topology & Controller View */}
        {activeTab === 'topology' && (
          <div className="space-y-6">
            {/* Interactive Topology Visualizer */}
            <TopologyCanvas
              servers={servers}
              currentMetrics={currentMetrics}
              lastSelectedServer={lastSelectedServer}
              activeAlgorithm={activeAlgorithm}
              onSelectServer={(srv) => setSelectedServerModal(srv)}
              trafficRate={trafficRate}
              onTriggerRequest={triggerSingleRequest}
              onAddServer={() => setShowAddServerModal(true)}
              onOpenFlowRules={() => setShowFlowModal(true)}
            />

            {/* Algorithm Selector */}
            <AlgorithmSelector
              algorithms={algorithms}
              activeAlgorithm={activeAlgorithm}
              onSwitchAlgorithm={switchAlgorithm}
            />

            {/* Simulation & Traffic Generator */}
            <SimulationPanel
              trafficRate={trafficRate}
              setTrafficRate={setTrafficRate}
              servers={servers}
              onToggleServerHealth={toggleServerHealth}
              onDrainServer={drainServer}
              trafficLogs={trafficLogs}
            />
          </div>
        )}


        {/* Tab 2: Benchmarking Laboratory View */}
        {activeTab === 'benchmark' && (
          <BenchmarkingLab addLog={addLog} />
        )}

        {/* Tab 3: TCP Congestion Control Lab */}
        {activeTab === 'tcplab' && <TcpLab addLog={addLog} />}
      </main>


      {/* Flow Table Modal */}
      {showFlowModal && (
        <FlowTableModal
          flowRules={flowRules}
          activeAlgorithm={activeAlgorithm}
          onClose={() => setShowFlowModal(false)}
        />
      )}

      {/* Add Server Modal */}
      <AddServerModal
        isOpen={showAddServerModal}
        onClose={() => setShowAddServerModal(false)}
        onAddServer={addServer}
        existingServers={servers}
        simulationMode={simulationMode}
      />

      {/* Server Detail Inspector Modal */}
      {selectedServerModal && (
        <ServerDetailModal
          server={
            servers.find(
              (s) =>
                (s.id || s.server_id) === (selectedServerModal.id || selectedServerModal.server_id)
            ) || selectedServerModal
          }
          metrics={currentMetrics[selectedServerModal.id || selectedServerModal.server_id]}
          onClose={() => setSelectedServerModal(null)}
          onToggleHealth={toggleServerHealth}
          onDrainServer={drainServer}
          onRemoveServer={removeServer}
          onUpdateWeight={updateServerWeight}
        />
      )}
    </div>
  );
}

