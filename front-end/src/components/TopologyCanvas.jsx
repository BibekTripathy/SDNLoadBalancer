import React, { useRef, useEffect, useState, useMemo } from 'react';
import {
  Server,
  Monitor,
  HardDrive,
  Cpu,
  Wifi,
  Activity,
  AlertOctagon,
  CheckCircle2,
  Play,
  Pause,
  Gauge,
  Plus,
  Clock,
} from 'lucide-react';

const PRESETS = [
  { label: 'Slow', speed: 0.35 },
  { label: 'Normal', speed: 0.55 },
  { label: 'Fast', speed: 1.20 },
];

export default function TopologyCanvas({
  servers = [],
  currentMetrics = {},
  lastSelectedServer,
  activeAlgorithm,
  onSelectServer,
  trafficRate = 0,
  onTriggerRequest,
  onAddServer,
}) {
  const canvasRef = useRef(null);
  const particlesRef = useRef([]);
  const animationFrameRef = useRef(null);

  // Animation speed state (persisted to localStorage)
  const [speedMultiplier, setSpeedMultiplier] = useState(() => {
    const saved = localStorage.getItem('sdn_packet_anim_speed');
    return saved !== null ? parseFloat(saved) : 0.55; // Default ~55% of original speed
  });

  const [isPaused, setIsPaused] = useState(() => {
    return localStorage.getItem('sdn_packet_anim_paused') === 'true';
  });

  // Keep refs updated for animation frame loop without triggering re-renders
  const speedMultiplierRef = useRef(speedMultiplier);
  const isPausedRef = useRef(isPaused);

  useEffect(() => {
    speedMultiplierRef.current = speedMultiplier;
    localStorage.setItem('sdn_packet_anim_speed', speedMultiplier.toString());
  }, [speedMultiplier]);

  useEffect(() => {
    isPausedRef.current = isPaused;
    localStorage.setItem('sdn_packet_anim_paused', isPaused.toString());
  }, [isPaused]);

  // Respect user preference for reduced motion
  useEffect(() => {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (!localStorage.getItem('sdn_packet_anim_speed')) {
        setSpeedMultiplier(0.25);
      }
    }
  }, []);

  // Compute dynamic canvas height & node positions for variable server pool
  const serverCount = Math.max(servers.length, 1);
  const canvasHeight = Math.max(420, serverCount * 95 + 40);
  const centerY = canvasHeight / 2;

  const nodes = useMemo(() => {
    const serverNodes = {};
    servers.forEach((srv, idx) => {
      const srvId = srv.id || srv.server_id;
      let yPos;
      if (serverCount === 1) {
        yPos = centerY;
      } else {
        const topMargin = 75;
        const bottomMargin = canvasHeight - 75;
        yPos = topMargin + (idx * (bottomMargin - topMargin)) / (serverCount - 1);
      }

      serverNodes[srvId] = {
        id: srvId,
        label: srv.label || `${srvId}`,
        ip: `${srv.ip}:${srv.port || 80}`,
        port: `Port ${srv.switch_port || idx + 2}`,
        x: 680,
        y: yPos,
        type: 'server',
      };
    });

    return {
      client: {
        id: 'client',
        label: 'Client (h1)',
        ip: '10.0.0.1',
        port: 'Port 1',
        x: 120,
        y: centerY,
        type: 'client',
      },
      switch: {
        id: 'switch',
        label: 'OVS Switch (s1)',
        ip: 'DPID: 0000...01',
        x: 380,
        y: centerY,
        type: 'switch',
      },
      controller: {
        id: 'controller',
        label: 'Ryu Controller (c0)',
        ip: '127.0.0.1:6653',
        x: 380,
        y: Math.max(65, centerY - 140),
        type: 'controller',
      },
      ...serverNodes,
    };
  }, [servers, serverCount, canvasHeight, centerY]);

  // Particle creation helper
  const spawnPacket = (fromNode, toNode, color = '#38BDF8', isReturn = false) => {
    if (!fromNode || !toNode) return;
    particlesRef.current.push({
      x: fromNode.x,
      y: fromNode.y,
      startX: fromNode.x,
      startY: fromNode.y,
      targetX: toNode.x,
      targetY: toNode.y,
      progress: 0,
      baseSpeed: 0.02 + Math.random() * 0.015,
      color,
      isReturn,
      toNodeId: toNode.id,
    });
  };

  // Periodically spawn traffic particles based on traffic rate
  useEffect(() => {
    if (trafficRate <= 0) return;

    const spawnInterval = setInterval(() => {
      // Find healthy or draining target (exclude DOWN)
      const eligibleServers = servers.filter(
        (s) => s.status === 'HEALTHY' || s.status === 'DRAINING'
      );
      if (eligibleServers.length === 0) return;

      const targetId =
        lastSelectedServer && eligibleServers.some((s) => (s.id || s.server_id) === lastSelectedServer)
          ? lastSelectedServer
          : eligibleServers[0].id || eligibleServers[0].server_id;

      const targetNode = nodes[targetId];

      if (targetNode && nodes.client && nodes.switch) {
        // Spawn request packet from Client -> Switch -> Server
        spawnPacket(nodes.client, nodes.switch, '#38BDF8');

        setTimeout(() => {
          spawnPacket(nodes.switch, targetNode, '#A855F7');
        }, 300);

        // Spawn response packet back from Server -> Switch -> Client
        setTimeout(() => {
          spawnPacket(targetNode, nodes.switch, '#34D399', true);
          setTimeout(() => {
            spawnPacket(nodes.switch, nodes.client, '#34D399', true);
          }, 300);
        }, 700);
      }
    }, Math.max(200, 15000 / Math.max(1, trafficRate)));

    return () => clearInterval(spawnInterval);
  }, [trafficRate, lastSelectedServer, servers, nodes]);

  // Whenever lastSelectedServer changes (e.g. Round Robin selection), immediately animate packet
  const prevSelectedRef = useRef(lastSelectedServer);
  useEffect(() => {
    if (!lastSelectedServer || !nodes[lastSelectedServer] || !nodes.client || !nodes.switch) return;
    if (prevSelectedRef.current === lastSelectedServer) return;
    prevSelectedRef.current = lastSelectedServer;

    const targetNode = nodes[lastSelectedServer];
    spawnPacket(nodes.client, nodes.switch, '#38BDF8');
    setTimeout(() => {
      spawnPacket(nodes.switch, targetNode, '#A855F7');
    }, 300);
    setTimeout(() => {
      spawnPacket(targetNode, nodes.switch, '#34D399', true);
      setTimeout(() => {
        spawnPacket(nodes.switch, nodes.client, '#34D399', true);
      }, 300);
    }, 700);
  }, [lastSelectedServer, nodes]);

  // Main canvas animation render loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw Connection Lines between Topology Nodes
      const drawLink = (from, to, isActive = false, isControl = false) => {
        if (!from || !to) return;
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.lineWidth = isActive ? 3 : isControl ? 2 : 1.5;

        if (isControl) {
          ctx.setLineDash([6, 6]);
          ctx.strokeStyle = '#818CF8';
        } else if (isActive) {
          ctx.setLineDash([]);
          ctx.strokeStyle = '#0284C7';
        } else {
          ctx.setLineDash([]);
          ctx.strokeStyle = '#1E293B';
        }
        ctx.stroke();
        ctx.setLineDash([]);
      };

      // Control link (Controller <-> Switch)
      if (nodes.controller && nodes.switch) {
        drawLink(nodes.controller, nodes.switch, false, true);
      }

      // Data link (Client <-> Switch)
      if (nodes.client && nodes.switch) {
        drawLink(nodes.client, nodes.switch, true, false);
      }

      // Data links (Switch <-> Servers)
      servers.forEach((srv) => {
        const srvId = srv.id || srv.server_id;
        const node = nodes[srvId];
        if (node && nodes.switch) {
          const isHealthy = srv.status === 'HEALTHY';
          const isDraining = srv.status === 'DRAINING';
          drawLink(nodes.switch, node, isHealthy || isDraining, false);
        }
      });

      // Update & Render Traffic Particles
      const activeParticles = [];
      const currentMultiplier = isPausedRef.current ? 0 : speedMultiplierRef.current;

      particlesRef.current.forEach((p) => {
        p.progress += p.baseSpeed * currentMultiplier;
        p.x = p.startX + (p.targetX - p.startX) * p.progress;
        p.y = p.startY + (p.targetY - p.startY) * p.progress;

        if (p.progress < 1.0) {
          // Draw particle glow
          ctx.beginPath();
          ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.shadowBlur = 10;
          ctx.shadowColor = p.color;
          ctx.fill();
          ctx.shadowBlur = 0;
          activeParticles.push(p);
        }
      });
      particlesRef.current = activeParticles;

      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    };
  }, [servers, nodes]);

  // Server counts for quick status
  const healthyCount = servers.filter((s) => s.status === 'HEALTHY').length;
  const drainingCount = servers.filter((s) => s.status === 'DRAINING').length;
  const downCount = servers.filter((s) => s.status === 'DOWN').length;

  return (
    <div className="glass-panel p-5 rounded-2xl relative overflow-hidden border border-slate-800 shadow-xl">
      {/* Header bar of topology visualizer */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-4 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Wifi className="w-5 h-5 text-sky-400" />
              SDN Topology Visualizer
            </h2>
            <div className="flex items-center gap-1.5 ml-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                {servers.length} {servers.length === 1 ? 'server' : 'servers'}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                {healthyCount} up
              </span>
              {drainingCount > 0 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/60 text-amber-400 border border-amber-800/60">
                  {drainingCount} draining
                </span>
              )}
              {downCount > 0 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950/60 text-red-400 border border-red-800/60">
                  {downCount} down
                </span>
              )}
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time packet routing, switch ports, and backend health visualization
          </p>
        </div>

        {/* Toolbar: Animation Speed Controls & Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Animation Speed Controller */}
          <div className="flex items-center gap-2 bg-slate-900/90 border border-slate-800 px-2.5 py-1.5 rounded-xl shadow-inner">
            <Gauge className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />
            <span className="text-[11px] font-mono text-slate-400">Speed:</span>

            {/* Presets */}
            <div className="flex items-center gap-1">
              {PRESETS.map((p) => {
                const isActive = Math.abs(speedMultiplier - p.speed) < 0.04;
                return (
                  <button
                    key={p.label}
                    onClick={() => setSpeedMultiplier(p.speed)}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono transition ${
                      isActive
                        ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold'
                        : 'bg-slate-800 text-slate-400 hover:text-slate-200 border border-transparent'
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>

            {/* Slider */}
            <input
              type="range"
              min="0.15"
              max="2.0"
              step="0.05"
              value={speedMultiplier}
              onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))}
              aria-label="Packet animation speed"
              className="w-16 accent-sky-400 bg-slate-800 h-1.5 rounded-lg cursor-pointer ml-1"
            />
            <span className="text-[11px] font-mono text-sky-300 w-10 text-right">
              {speedMultiplier.toFixed(2)}x
            </span>

            {/* Pause / Resume Button */}
            <button
              onClick={() => setIsPaused((prev) => !prev)}
              title={isPaused ? 'Resume packet animation' : 'Pause packet animation'}
              className={`p-1 rounded-lg border transition ml-1 flex items-center justify-center ${
                isPaused
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
              }`}
            >
              {isPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            </button>
          </div>

          {/* Action buttons */}
          {onAddServer && (
            <button
              onClick={onAddServer}
              className="px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 shadow-sm active:scale-95"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Server
            </button>
          )}

          <button
            onClick={onTriggerRequest}
            className="px-3 py-1.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 shadow-sm active:scale-95"
          >
            <Activity className="w-3.5 h-3.5" />
            Send HTTP GET
          </button>
        </div>
      </div>

      {/* Topology Canvas Layer */}
      <div
        className="relative w-full overflow-x-auto flex justify-center items-center"
        style={{ minHeight: `${canvasHeight}px` }}
      >
        <canvas
          ref={canvasRef}
          width={820}
          height={canvasHeight}
          className="absolute inset-0 w-full h-full pointer-events-none z-10"
        />

        {/* DOM Node Overlay Components for rich UI cards */}
        <div
          className="relative w-[820px] flex-shrink-0 z-20 pointer-events-auto"
          style={{ height: `${canvasHeight}px` }}
        >
          {/* CLIENT NODE */}
          {nodes.client && (
            <div
              style={{ left: `${nodes.client.x - 65}px`, top: `${nodes.client.y - 45}px` }}
              className="absolute w-32 p-3 bg-slate-900/90 border border-sky-500/40 rounded-xl text-center shadow-lg hover:border-sky-400 transition"
            >
              <Monitor className="w-6 h-6 text-sky-400 mx-auto mb-1" />
              <div className="text-xs font-bold text-slate-200">{nodes.client.label}</div>
              <div className="text-[10px] font-mono text-sky-300">{nodes.client.ip}</div>
              <div className="mt-1 text-[9px] bg-sky-950 text-sky-400 px-1.5 py-0.5 rounded border border-sky-800 inline-block font-mono">
                Port 1
              </div>
            </div>
          )}

          {/* CONTROLLER NODE */}
          {nodes.controller && (
            <div
              style={{ left: `${nodes.controller.x - 75}px`, top: `${nodes.controller.y - 45}px` }}
              className="absolute w-36 p-3 bg-slate-900/90 border border-purple-500/50 rounded-xl text-center shadow-lg hover:border-purple-400 transition"
            >
              <Cpu className="w-6 h-6 text-purple-400 mx-auto mb-1 animate-pulse" />
              <div className="text-xs font-bold text-purple-200">{nodes.controller.label}</div>
              <div className="text-[10px] font-mono text-purple-300">{nodes.controller.ip}</div>
              <div className="mt-1 text-[9px] bg-purple-950 text-purple-300 px-1.5 py-0.5 rounded border border-purple-800 inline-block font-mono">
                OpenFlow 1.3
              </div>
            </div>
          )}

          {/* SWITCH NODE */}
          {nodes.switch && (
            <div
              style={{ left: `${nodes.switch.x - 65}px`, top: `${nodes.switch.y - 45}px` }}
              className="absolute w-32 p-3 bg-slate-900/90 border border-indigo-500/50 rounded-xl text-center shadow-lg hover:border-indigo-400 transition cursor-pointer"
            >
              <HardDrive className="w-6 h-6 text-indigo-400 mx-auto mb-1" />
              <div className="text-xs font-bold text-slate-200">{nodes.switch.label}</div>
              <div className="text-[10px] font-mono text-indigo-300">OVS Kernel</div>
              <div className="mt-1 text-[9px] bg-indigo-950 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-800 inline-block font-mono">
                Ports 1-{Math.max(4, servers.length + 1)}
              </div>
            </div>
          )}

          {/* BACKEND SERVER NODES */}
          {servers.map((srv) => {
            const srvId = srv.id || srv.server_id;
            const node = nodes[srvId];
            if (!node) return null;
            const metrics = currentMetrics[srvId] || {};
            const isHealthy = srv.status === 'HEALTHY';
            const isDraining = srv.status === 'DRAINING';
            const isDown = srv.status === 'DOWN';
            const isChosen = lastSelectedServer === srvId && (isHealthy || isDraining);

            return (
              <div
                key={srvId}
                onClick={() => onSelectServer(srv)}
                style={{ left: `${node.x - 70}px`, top: `${node.y - 45}px` }}
                className={`absolute w-36 p-3 bg-slate-900/95 rounded-xl border text-center shadow-xl cursor-pointer transition transform hover:scale-105 ${
                  isDown
                    ? 'border-red-500/50 shadow-red-500/10'
                    : isDraining
                    ? 'border-amber-500/50 shadow-amber-500/10 ring-1 ring-amber-500/30'
                    : isChosen
                    ? 'border-emerald-400 ring-2 ring-emerald-400/30 shadow-emerald-500/20'
                    : 'border-slate-800 hover:border-slate-600'
                }`}
              >
                {/* Node icon & health indicator */}
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-mono font-bold text-slate-400">{node.port}</span>
                  {isHealthy ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  ) : isDraining ? (
                    <Clock className="w-3.5 h-3.5 text-amber-400 animate-spin" />
                  ) : (
                    <AlertOctagon className="w-3.5 h-3.5 text-red-400 animate-bounce" />
                  )}
                </div>

                <Server
                  className={`w-6 h-6 mx-auto mb-1 ${
                    isHealthy
                      ? isChosen
                        ? 'text-emerald-400'
                        : 'text-sky-400'
                      : isDraining
                      ? 'text-amber-400'
                      : 'text-red-400'
                  }`}
                />

                <div className="text-xs font-bold text-slate-200 flex items-center justify-center gap-1">
                  <span>{srvId}</span>
                  {srv.weight && (
                    <span className="text-[9px] font-mono text-purple-300 bg-purple-950/80 px-1 rounded border border-purple-800">
                      w{srv.weight}
                    </span>
                  )}
                </div>
                <div className="text-[10px] font-mono text-slate-400">{srv.ip}</div>

                {/* Metrics preview pill */}
                <div className="mt-2 pt-1.5 border-t border-slate-800 flex justify-between text-[9px] font-mono">
                  <span className="text-slate-400">Bw:</span>
                  <span className={isHealthy || isDraining ? 'text-sky-300 font-bold' : 'text-slate-600'}>
                    {isHealthy || isDraining ? `${metrics.bandwidth_mbps || 0}M` : '0M'}
                  </span>

                  <span className="text-slate-400">Conn:</span>
                  <span className={isHealthy || isDraining ? 'text-emerald-300 font-bold' : 'text-slate-600'}>
                    {isHealthy || isDraining ? metrics.active_connections || 0 : 0}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend Footer */}
      <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs font-mono text-slate-400">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block shadow-sm shadow-sky-400" />
            <span>HTTP Request Packet</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block shadow-sm shadow-emerald-400" />
            <span>Server Response Packet</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-400 inline-block shadow-sm shadow-purple-400" />
            <span>OpenFlow 1.3 Control Link</span>
          </div>
        </div>
        <div className="text-[11px] text-slate-500">
          Click any backend server node to inspect status, configure weight, drain, or simulate failure.
        </div>
      </div>
    </div>
  );
}

