import React, { useRef, useEffect, useState, useMemo, useLayoutEffect } from 'react';
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
  Zap,
} from 'lucide-react';

const PRESETS = [
  { label: 'Slow', speed: 0.35 },
  { label: 'Normal', speed: 0.55 },
  { label: 'Fast', speed: 1.20 },
];

// Catppuccin Latte accents used for nodes, links and packets
const C = {
  teal: '#179299',
  sky: '#04a5e5',
  green: '#40a02b',
  lightGreen: '#8fc486', // green mixed 55% into the Latte base
  yellow: '#df8e1d',
  peach: '#fe640b',
  red: '#d20f39',
  mauve: '#8839ef',
  lavender: '#7287fd',
  overlay: '#9ca0b0',
};

// Layout constants (px). The stage grows one ROW_H per server.
const MIN_WIDTH = 780;
const MIN_HEIGHT = 460;
const ROW_H = 128;
const CLIENT = { w: 150, h: 104 };
const SWITCH = { w: 160, h: 108 };
const CONTROLLER = { w: 176, h: 104 };
const SERVER = { w: 172, h: 112 };

// Active backend: green; healthy standby: light green; draining: yellow; anything else: red
const serverAccent = (status, isChosen) => {
  if (status === 'DRAINING') return C.yellow;
  if (status !== 'HEALTHY') return C.red;
  return isChosen ? C.green : C.lightGreen;
};

// Polyline -> SVG path with rounded elbows
const toPath = (pts, r = 10) => {
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1];
    const [x, y] = pts[i];
    const [nx, ny] = pts[i + 1];
    const inLen = Math.hypot(x - px, y - py);
    const outLen = Math.hypot(nx - x, ny - y);
    const rr = Math.min(r, inLen / 2, outLen / 2);
    if (rr < 1) {
      d += ` L ${x} ${y}`;
      continue;
    }
    const ax = x - ((x - px) / inLen) * rr;
    const ay = y - ((y - py) / inLen) * rr;
    const bx = x + ((nx - x) / outLen) * rr;
    const by = y + ((ny - y) / outLen) * rr;
    d += ` L ${ax} ${ay} Q ${x} ${y} ${bx} ${by}`;
  }
  const [lx, ly] = pts[pts.length - 1];
  return `${d} L ${lx} ${ly}`;
};

// Point at fraction t (0..1) along a polyline
const pointAlong = (pts, t) => {
  const segs = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const len = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    segs.push(len);
    total += len;
  }
  let dist = t * total;
  for (let i = 0; i < segs.length; i++) {
    if (dist <= segs[i] || i === segs.length - 1) {
      const f = segs[i] === 0 ? 0 : Math.min(1, dist / segs[i]);
      return [
        pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
        pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f,
      ];
    }
    dist -= segs[i];
  }
  return pts[pts.length - 1];
};

// A link is a wide translucent halo under a solid stroke so it reads on the hatched background
function Link({ pts, color, width = 3, dashed = false, faded = false }) {
  const d = toPath(pts);
  return (
    <g opacity={faded ? 0.55 : 1}>
      <path d={d} fill="none" stroke={color} strokeOpacity="0.18" strokeWidth={width + 7} strokeLinecap="round" strokeLinejoin="round" />
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={dashed ? '7 7' : undefined}
      />
    </g>
  );
};

export default function TopologyCanvas({
  servers = [],
  currentMetrics = {},
  lastSelectedServer,
  activeAlgorithm,
  onSelectServer,
  trafficRate = 0,
  onTriggerRequest,
  onAddServer,
  onOpenFlowRules,
}) {
  const stageWrapRef = useRef(null);
  const canvasRef = useRef(null);
  const particlesRef = useRef([]);
  const animationFrameRef = useRef(null);
  const [stageWidth, setStageWidth] = useState(MIN_WIDTH);
  const [needsScroll, setNeedsScroll] = useState(false);

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

  // Stage follows the panel width; below MIN_WIDTH it scrolls horizontally
  useLayoutEffect(() => {
    const el = stageWrapRef.current;
    if (!el) return;
    const update = () => {
      const available = Math.floor(el.clientWidth);
      setStageWidth(Math.max(MIN_WIDTH, available));
      setNeedsScroll(available < MIN_WIDTH);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const serverCount = Math.max(servers.length, 1);
  const stageHeight = Math.max(MIN_HEIGHT, serverCount * ROW_H + 40);

  // Node centres and link geometry for a variable server pool
  const layout = useMemo(() => {
    const W = stageWidth;
    const centerY = stageHeight / 2;
    const mid = (servers.length - 1) / 2;

    const client = { x: 30 + CLIENT.w / 2, y: centerY };
    const sw = { x: Math.round(W * 0.4), y: centerY };
    const controller = { x: sw.x, y: Math.max(CONTROLLER.h / 2 + 16, centerY - 170) };
    const serverX = W - 30 - SERVER.w / 2;

    const swRight = sw.x + SWITCH.w / 2;
    const srvLeft = serverX - SERVER.w / 2;
    const laneStart = swRight + 36;
    const laneEnd = Math.max(laneStart, srvLeft - 36);
    const exitStep = servers.length > 1 ? Math.min(16, (SWITCH.h - 28) / (servers.length - 1)) : 0;

    // Each server gets its own exit point on the switch and its own vertical
    // lane. Outer servers turn nearest the switch so no two links cross.
    const serverNodes = {};
    servers.forEach((srv, idx) => {
      const id = srv.id || srv.server_id;
      const offset = idx - mid;
      const y = centerY + offset * ROW_H;
      const exitY = centerY + offset * exitStep;
      const d = mid === 0 ? 0 : Math.abs(offset) / mid;
      const laneX = laneStart + (1 - d) * (laneEnd - laneStart);
      serverNodes[id] = {
        id,
        x: serverX,
        y,
        port: `Port ${srv.switch_port || idx + 2}`,
        path: [
          [swRight, exitY],
          [laneX, exitY],
          [laneX, y],
          [srvLeft, y],
        ],
      };
    });

    return {
      client,
      sw,
      controller,
      servers: serverNodes,
      clientPath: [
        [client.x + CLIENT.w / 2, centerY],
        [sw.x - SWITCH.w / 2, centerY],
      ],
      controlPath: [
        [sw.x, controller.y + CONTROLLER.h / 2],
        [sw.x, centerY - SWITCH.h / 2],
      ],
    };
  }, [servers, stageWidth, stageHeight]);

  // Particle creation helper: travels along a polyline, optionally reversed
  const spawnPacket = (path, color, reverse = false) => {
    if (!path) return;
    particlesRef.current.push({
      path: reverse ? [...path].reverse() : path,
      progress: 0,
      baseSpeed: 0.02 + Math.random() * 0.015,
      color,
    });
  };

  // Request client -> switch -> server, then response back
  const animateExchange = (targetId) => {
    const target = layout.servers[targetId];
    if (!target) return;
    spawnPacket(layout.clientPath, C.sky);
    setTimeout(() => spawnPacket(target.path, C.mauve), 300);
    setTimeout(() => {
      spawnPacket(target.path, C.green, true);
      setTimeout(() => spawnPacket(layout.clientPath, C.green, true), 300);
    }, 700);
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

      animateExchange(targetId);
    }, Math.max(200, 15000 / Math.max(1, trafficRate)));

    return () => clearInterval(spawnInterval);
  }, [trafficRate, lastSelectedServer, servers, layout]);

  // Whenever lastSelectedServer changes (e.g. Round Robin selection), immediately animate packet
  const prevSelectedRef = useRef(lastSelectedServer);
  useEffect(() => {
    if (!lastSelectedServer || !layout.servers[lastSelectedServer]) return;
    if (prevSelectedRef.current === lastSelectedServer) return;
    prevSelectedRef.current = lastSelectedServer;
    animateExchange(lastSelectedServer);
  }, [lastSelectedServer, layout]);

  // Packet animation loop. Links are drawn in SVG; the canvas only holds packets.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = stageWidth * dpr;
    canvas.height = stageHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Packets in flight were laid out for the old stage size
    particlesRef.current = [];

    const render = () => {
      ctx.clearRect(0, 0, stageWidth, stageHeight);
      const currentMultiplier = isPausedRef.current ? 0 : speedMultiplierRef.current;
      const activeParticles = [];

      particlesRef.current.forEach((p) => {
        p.progress += p.baseSpeed * currentMultiplier;
        if (p.progress >= 1.0) return;
        const [x, y] = pointAlong(p.path, p.progress);
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}33`;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x, y, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = '#eff1f5';
        ctx.stroke();
        activeParticles.push(p);
      });
      particlesRef.current = activeParticles;

      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
    };
  }, [stageWidth, stageHeight]);

  // Server counts for quick status
  const healthyCount = servers.filter((s) => s.status === 'HEALTHY').length;
  const drainingCount = servers.filter((s) => s.status === 'DRAINING').length;
  const downCount = servers.filter((s) => s.status === 'DOWN').length;

  const cardPos = (node, size) => ({
    left: `${node.x - size.w / 2}px`,
    top: `${node.y - size.h / 2}px`,
    width: `${size.w}px`,
    height: `${size.h}px`,
  });

  return (
    <div className="glass-panel p-5 rounded-2xl relative overflow-hidden border border-slate-800">
      {/* Header bar of topology visualizer */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-4 border-b border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Wifi className="w-5 h-5 text-sky-400" />
              SDN Topology Visualizer
            </h2>
            <div className="flex items-center gap-1.5 ml-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700">
                {servers.length} {servers.length === 1 ? 'server' : 'servers'}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                {healthyCount} up
              </span>
              {drainingCount > 0 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">
                  {drainingCount} draining
                </span>
              )}
              {downCount > 0 && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950 text-red-300 border border-red-800">
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
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-2.5 py-1.5 rounded-xl">
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
                        ? 'bg-sky-500/20 text-sky-200 border border-sky-500/40 font-bold'
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
              className="w-16 accent-sky-400 h-1.5 rounded-lg cursor-pointer ml-1"
            />
            <span className="text-[11px] font-mono text-sky-200 w-10 text-right">
              {speedMultiplier.toFixed(2)}x
            </span>

            {/* Pause / Resume Button */}
            <button
              onClick={() => setIsPaused((prev) => !prev)}
              title={isPaused ? 'Resume packet animation' : 'Pause packet animation'}
              className={`p-1 rounded-lg border transition ml-1 flex items-center justify-center ${
                isPaused
                  ? 'bg-amber-500/20 text-amber-200 border-amber-500/40 hover:bg-amber-500/30'
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
              className="px-3 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 active:scale-95"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Server
            </button>
          )}

          <button
            onClick={onTriggerRequest}
            className="px-3 py-1.5 bg-sky-500/15 hover:bg-sky-500/25 text-sky-200 border border-sky-500/40 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 active:scale-95"
          >
            <Activity className="w-3.5 h-3.5" />
            Send HTTP GET
          </button>
        </div>
      </div>

      {/* Topology stage: SVG links, packet canvas and DOM cards share one coordinate box */}
      <div
        ref={stageWrapRef}
        className={`w-full custom-scrollbar ${needsScroll ? 'overflow-x-auto overflow-y-hidden' : 'overflow-hidden'}`}
      >
        <div
          className="relative rounded-xl ring-1 ring-slate-800"
          style={{
            width: `${stageWidth}px`,
            height: `${stageHeight}px`,
            backgroundColor: 'var(--ctp-mantle)',
            backgroundImage: 'radial-gradient(#bcc0cc 1px, transparent 1px)',
            backgroundSize: '22px 22px',
          }}
        >
          <svg
            width={stageWidth}
            height={stageHeight}
            className="absolute inset-0 pointer-events-none"
            aria-hidden="true"
          >
            <Link pts={layout.controlPath} color={C.mauve} width={2.5} dashed />
            <Link pts={layout.clientPath} color={C.teal} width={3.5} />
            {servers.map((srv) => {
              const id = srv.id || srv.server_id;
              const node = layout.servers[id];
              if (!node) return null;
              const isUp = srv.status === 'HEALTHY' || srv.status === 'DRAINING';
              const isChosen = lastSelectedServer === id && srv.status === 'HEALTHY';
              return (
                <Link
                  key={id}
                  pts={node.path}
                  color={serverAccent(srv.status, isChosen)}
                  width={isChosen ? 4 : 3}
                  dashed={!isUp}
                  faded={!isUp}
                />
              );
            })}
          </svg>

          <canvas
            ref={canvasRef}
            style={{ width: `${stageWidth}px`, height: `${stageHeight}px` }}
            className="absolute inset-0 pointer-events-none z-10"
          />

          {/* Active algorithm, pinned to the stage corner above the client */}
          <div className="absolute z-30 left-4 top-4 flex items-center gap-2 px-3 py-1.5 rounded-lg border border-amber-800 bg-amber-950 text-xs font-mono whitespace-nowrap">
            <Zap className="w-4 h-4 text-amber-400" />
            <span className="text-slate-400">Algorithm:</span>
            <span className="text-amber-200 font-bold uppercase">{(activeAlgorithm || '').replace(/_/g, ' ')}</span>
          </div>

          {/* CLIENT NODE */}
          <div
            style={{ ...cardPos(layout.client, CLIENT), '--accent': C.teal }}
            className="sketch-card absolute z-20 p-3 text-center flex flex-col items-center justify-center"
          >
            <Monitor className="w-6 h-6 mb-1" style={{ color: C.teal }} />
            <div className="text-xs font-bold">Client (h1)</div>
            <div className="text-[10px] font-mono text-slate-400">10.0.0.1</div>
            <div className="sketch-chip mt-1 text-[9px] px-1.5 py-0.5 rounded font-mono">Port 1</div>
          </div>

          {/* CONTROLLER NODE */}
          <div
            style={{ ...cardPos(layout.controller, CONTROLLER), '--accent': C.mauve }}
            className="sketch-card absolute z-20 p-3 text-center flex flex-col items-center justify-center"
          >
            <Cpu className="w-6 h-6 mb-1" style={{ color: C.mauve }} />
            <div className="text-xs font-bold">Ryu Controller (c0)</div>
            <div className="text-[10px] font-mono text-slate-400">127.0.0.1:6653</div>
            <div className="sketch-chip mt-1 text-[9px] px-1.5 py-0.5 rounded font-mono">OpenFlow 1.3</div>
          </div>

          {/* SWITCH NODE */}
          <div
            onClick={onOpenFlowRules}
            title="View OpenFlow flow table"
            style={{ ...cardPos(layout.sw, SWITCH), '--accent': C.lavender }}
            className="sketch-card absolute z-20 p-3 text-center flex flex-col items-center justify-center cursor-pointer transition-transform hover:scale-[1.03]"
          >
            <HardDrive className="w-6 h-6 mb-1" style={{ color: C.lavender }} />
            <div className="text-xs font-bold">OVS Switch (s1)</div>
            <div className="text-[10px] font-mono text-slate-400">OVS Kernel</div>
            <div className="sketch-chip mt-1 text-[9px] px-1.5 py-0.5 rounded font-mono">
              Ports 1-{Math.max(4, servers.length + 1)}
            </div>
          </div>

          {/* BACKEND SERVER NODES */}
          {servers.map((srv) => {
            const srvId = srv.id || srv.server_id;
            const node = layout.servers[srvId];
            if (!node) return null;
            const metrics = currentMetrics[srvId] || {};
            const isHealthy = srv.status === 'HEALTHY';
            const isDraining = srv.status === 'DRAINING';
            const isChosen = lastSelectedServer === srvId && isHealthy;
            const accent = serverAccent(srv.status, isChosen);

            return (
              <div
                key={srvId}
                onClick={() => onSelectServer(srv)}
                style={{ ...cardPos(node, SERVER), '--accent': accent }}
                className={`sketch-card ${isChosen ? 'sketch-card-active' : ''} absolute z-20 px-3 pt-2 pb-1.5 text-center cursor-pointer transition-transform hover:scale-[1.03] flex flex-col`}
              >
                {/* Port & health indicator */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold text-slate-400">{node.port}</span>
                  {isHealthy ? (
                    <CheckCircle2 className="w-3.5 h-3.5" style={{ color: accent }} />
                  ) : isDraining ? (
                    <Clock className="w-3.5 h-3.5 animate-spin" style={{ color: accent }} />
                  ) : (
                    <AlertOctagon className="w-3.5 h-3.5 animate-bounce" style={{ color: accent }} />
                  )}
                </div>

                <Server className="w-5 h-5 mx-auto" style={{ color: accent }} />

                <div className="text-xs font-bold flex items-center justify-center gap-1 mt-0.5">
                  <span className="truncate">{srv.label || srvId}</span>
                  {srv.weight && (
                    <span className="sketch-chip text-[9px] font-mono px-1 rounded">w{srv.weight}</span>
                  )}
                </div>
                <div className="text-[10px] font-mono text-slate-400">{srv.ip}</div>

                {/* Metrics preview */}
                <div className="mt-auto pt-1 border-t border-slate-700 flex justify-between text-[9px] font-mono">
                  <span className="text-slate-400">Bw:</span>
                  <span className={isHealthy || isDraining ? 'text-sky-200 font-bold' : 'text-slate-500'}>
                    {isHealthy || isDraining ? `${metrics.bandwidth_mbps || 0}M` : '0M'}
                  </span>

                  <span className="text-slate-400">Conn:</span>
                  <span className={isHealthy || isDraining ? 'text-emerald-200 font-bold' : 'text-slate-500'}>
                    {isHealthy || isDraining ? metrics.active_connections || 0 : 0}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs font-mono text-slate-400">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: C.sky }} />
            <span>HTTP Request Packet</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: C.green }} />
            <span>Server Response Packet</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0 border-t-2 border-dashed inline-block" style={{ borderColor: C.mauve }} />
            <span>OpenFlow 1.3 Control Link</span>
          </div>
          {[
            ['Active', C.green],
            ['Standby', C.lightGreen],
            ['Draining', C.yellow],
            ['Down', C.red],
          ].map(([label, color]) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm border-2 inline-block" style={{ borderColor: color }} />
              <span>{label}</span>
            </div>
          ))}
        </div>
        <div className="text-[11px] text-slate-500">
          Click any backend server node to inspect status, configure weight, drain, or simulate failure.
        </div>
      </div>
    </div>
  );
}
