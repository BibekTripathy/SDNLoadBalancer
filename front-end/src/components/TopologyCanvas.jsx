import React, { useRef, useEffect, useState } from 'react';
import { Server, Monitor, HardDrive, Cpu, Wifi, Activity, AlertOctagon, CheckCircle2, ShieldAlert } from 'lucide-react';

export default function TopologyCanvas({
  servers,
  currentMetrics,
  lastSelectedServer,
  activeAlgorithm,
  onSelectServer,
  trafficRate,
  onTriggerRequest,
}) {
  const canvasRef = useRef(null);
  const particlesRef = useRef([]);
  const animationFrameRef = useRef(null);

  // Position definitions for topology nodes
  const nodes = {
    client: { id: 'client', label: 'Client (h1)', ip: '10.0.0.1', port: 'Port 1', x: 120, y: 220, type: 'client' },
    switch: { id: 'switch', label: 'OVS Switch (s1)', ip: 'DPID: 0000...01', x: 380, y: 220, type: 'switch' },
    controller: { id: 'controller', label: 'Ryu Controller (c0)', ip: '127.0.0.1:6653', x: 380, y: 70, type: 'controller' },
    server1: { id: 'server1', label: 'Server 1 (h2)', ip: '10.0.0.2:80', port: 'Port 2', x: 680, y: 110, type: 'server' },
    server2: { id: 'server2', label: 'Server 2 (h3)', ip: '10.0.0.3:80', port: 'Port 3', x: 680, y: 220, type: 'server' },
    server3: { id: 'server3', label: 'Server 3 (h4)', ip: '10.0.0.4:80', port: 'Port 4', x: 680, y: 330, type: 'server' },
  };

  // Particle creation helper
  const spawnPacket = (fromNode, toNode, color = '#38BDF8', isReturn = false) => {
    particlesRef.current.push({
      x: fromNode.x,
      y: fromNode.y,
      startX: fromNode.x,
      startY: fromNode.y,
      targetX: toNode.x,
      targetY: toNode.y,
      progress: 0,
      speed: 0.02 + Math.random() * 0.015,
      color,
      isReturn,
      toNodeId: toNode.id,
    });
  };

  // Periodically spawn traffic particles based on traffic rate
  useEffect(() => {
    if (trafficRate <= 0) return;

    const spawnInterval = setInterval(() => {
      // Find healthy target
      const healthyServers = servers.filter((s) => s.status === 'HEALTHY');
      if (healthyServers.length === 0) return;

      const targetId = lastSelectedServer && healthyServers.some((s) => s.id === lastSelectedServer)
        ? lastSelectedServer
        : healthyServers[0].id;

      const targetNode = nodes[targetId];

      if (targetNode) {
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
  }, [trafficRate, lastSelectedServer, servers]);

  // Main canvas animation render loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw Connection Lines between Topology Nodes
      const drawLink = (from, to, isActive = false, isControl = false) => {
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
      drawLink(nodes.controller, nodes.switch, false, true);

      // Data link (Client <-> Switch)
      drawLink(nodes.client, nodes.switch, true, false);

      // Data links (Switch <-> Servers)
      servers.forEach((srv) => {
        const srvId = srv.id || srv.server_id;
        const node = nodes[srvId];
        if (node) {
          const isHealthy = srv.status === 'HEALTHY';
          drawLink(nodes.switch, node, isHealthy, false);
        }
      });

      // Update & Render Traffic Particles
      const activeParticles = [];
      particlesRef.current.forEach((p) => {
        p.progress += p.speed;
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
  }, [servers]);

  return (
    <div className="glass-panel p-5 rounded-2xl relative overflow-hidden border border-slate-800 shadow-xl">
      {/* Header bar of topology visualizer */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Wifi className="w-5 h-5 text-sky-400" />
            SDN Topology Visualizer
          </h2>
          <p className="text-xs text-slate-400">
            Real-time packet routing, switch ports, and backend health visualization
          </p>
        </div>

        <div className="flex items-center gap-2">
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
      <div className="relative w-full overflow-x-auto min-h-[400px] flex justify-center items-center">
        <canvas
          ref={canvasRef}
          width={820}
          height={420}
          className="absolute inset-0 w-full h-full pointer-events-none z-10"
        />

        {/* DOM Node Overlay Components for rich UI cards */}
        <div className="relative w-[820px] h-[420px] flex-shrink-0 z-20 pointer-events-auto">
          {/* CLIENT NODE */}
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

          {/* CONTROLLER NODE */}
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

          {/* SWITCH NODE */}
          <div
            style={{ left: `${nodes.switch.x - 65}px`, top: `${nodes.switch.y - 45}px` }}
            className="absolute w-32 p-3 bg-slate-900/90 border border-indigo-500/50 rounded-xl text-center shadow-lg hover:border-indigo-400 transition cursor-pointer"
          >
            <HardDrive className="w-6 h-6 text-indigo-400 mx-auto mb-1" />
            <div className="text-xs font-bold text-slate-200">{nodes.switch.label}</div>
            <div className="text-[10px] font-mono text-indigo-300">OVS Kernel</div>
            <div className="mt-1 text-[9px] bg-indigo-950 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-800 inline-block font-mono">
              Ports 1-4
            </div>
          </div>

          {/* BACKEND SERVER NODES */}
          {servers.map((srv) => {
            const srvId = srv.id || srv.server_id;
            const node = nodes[srvId];
            if (!node) return null;
            const metrics = currentMetrics[srvId] || {};
            const isHealthy = srv.status === 'HEALTHY';
            const isDown = srv.status === 'DOWN';
            const isChosen = lastSelectedServer === srvId && isHealthy;

            return (
              <div
                key={srvId}
                onClick={() => onSelectServer(srv)}
                style={{ left: `${node.x - 70}px`, top: `${node.y - 45}px` }}
                className={`absolute w-36 p-3 bg-slate-900/95 rounded-xl border text-center shadow-xl cursor-pointer transition transform hover:scale-105 ${
                  isDown
                    ? 'border-red-500/50 shadow-red-500/10'
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
                  ) : (
                    <AlertOctagon className="w-3.5 h-3.5 text-red-400 animate-bounce" />
                  )}
                </div>

                <Server
                  className={`w-6 h-6 mx-auto mb-1 ${
                    isHealthy ? (isChosen ? 'text-emerald-400' : 'text-sky-400') : 'text-red-400'
                  }`}
                />

                <div className="text-xs font-bold text-slate-200">{srvId}</div>
                <div className="text-[10px] font-mono text-slate-400">{srv.ip}</div>

                {/* Metrics preview pill */}
                <div className="mt-2 pt-1.5 border-t border-slate-800 flex justify-between text-[9px] font-mono">
                  <span className="text-slate-400">Bw:</span>
                  <span className={isHealthy ? 'text-sky-300 font-bold' : 'text-slate-600'}>
                    {isHealthy ? `${metrics.bandwidth_mbps || 0}M` : '0M'}
                  </span>

                  <span className="text-slate-400">Conn:</span>
                  <span className={isHealthy ? 'text-emerald-300 font-bold' : 'text-slate-600'}>
                    {isHealthy ? metrics.active_connections || 0 : 0}
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
          Click any backend server node to inspect status, change weight, or simulate failure.
        </div>
      </div>
    </div>
  );
}
