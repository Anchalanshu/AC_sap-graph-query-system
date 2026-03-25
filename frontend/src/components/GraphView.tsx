import React, { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import axios from "axios";
import { Minus, Plus, RotateCcw } from "lucide-react";

export type GraphNode = {
  id: string;
  type: string;
  label: string;
  color?: string;
  data?: Record<string, unknown>;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
};

export type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  label: string;
};

export type GraphData = {
  nodes: GraphNode[];
  links: GraphLink[];
};

type GraphApiResponse = {
  nodes: Array<{ id: string; label: string; type: string }>;
  edges: Array<{ source: string; target: string; label: string }>;
};

type Props = {
  graphOverride?: GraphData | null;
  highlightedNodeIds: string[];
  onNodeClick: (node: GraphNode | null) => void;
  onLoaded: (g: GraphData) => void;
  onError: (msg: string) => void;
};

const NODE_SIZES: Record<string, number> = {
  Customer: 11,
  SalesOrder: 12,
  Material: 8,
  Plant: 10,
  Delivery: 10,
};

const LEGEND: Array<{ type: string; color: string }> = [
  { type: "Customer", color: "#3B82F6" }, // blue
  { type: "SalesOrder", color: "#7C3AED" }, // purple
  { type: "Material", color: "#10B981" }, // green
  { type: "Plant", color: "#F59E0B" }, // orange
  { type: "Delivery", color: "#EF4444" } // red
];

export default function GraphView({
  graphOverride,
  highlightedNodeIds,
  onNodeClick,
  onLoaded,
  onError
}: Props) {
  const fgRef = useRef<ForceGraphMethods>();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [pulseT, setPulseT] = useState(0);

  const highlighted = useMemo(() => new Set(highlightedNodeIds), [highlightedNodeIds]);

  useEffect(() => {
    let raf = 0;
    const loop = () => {
      setPulseT((t) => (t + 1) % 120);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (graphOverride) {
      setData(graphOverride);
      setLoading(false);
      onLoaded(graphOverride);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const res = await axios.get<GraphApiResponse>("/api/graph");
        if (cancelled) return;
        const g: GraphData = {
          nodes: res.data.nodes.map((n) => ({
            id: n.id,
            label: n.label,
            type: n.type,
            data: {}
          })),
          links: res.data.edges.map((e) => ({
            source: e.source,
            target: e.target,
            label: e.label
          }))
        };
        setData(g);
        onLoaded(g);
      } catch (e: any) {
        onError(e?.message || "Failed to load graph");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [graphOverride, onError, onLoaded]);

  useEffect(() => {
    if (!data || highlightedNodeIds.length === 0) return;
    const nodesById = new Map(data.nodes.map((n) => [n.id, n]));
    const pts = highlightedNodeIds
      .map((id) => nodesById.get(id))
      .filter(Boolean) as GraphNode[];

    if (pts.length === 0) return;
    const xs = pts.map((n) => n.x ?? 0);
    const ys = pts.map((n) => n.y ?? 0);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;

    fgRef.current?.centerAt(cx, cy, 700);
    fgRef.current?.zoom(2.2, 700);
  }, [data, highlightedNodeIds]);

  const drawNode = (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const n = node as GraphNode;
    const rBase = NODE_SIZES[n.type] ?? 7;
    const r = rBase;

    const isHighlighted = highlighted.has(n.id);
    const pulse = isHighlighted ? 1 + 0.18 * Math.sin((pulseT / 120) * Math.PI * 2) : 1;
    const color =
      n.color ||
      LEGEND.find((l) => l.type === n.type)?.color ||
      "#94A3B8";

    // glow ring
    if (isHighlighted) {
      ctx.beginPath();
      ctx.arc(n.x || 0, n.y || 0, r * 1.9 * pulse, 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(250, 204, 21, 0.95)";
      ctx.lineWidth = Math.max(2, 3 / globalScale);
      ctx.shadowColor = "rgba(250, 204, 21, 0.75)";
      ctx.shadowBlur = 22;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // node body
    ctx.beginPath();
    ctx.arc(n.x || 0, n.y || 0, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    // label
    const label = n.label ?? n.id;
    const fontSize = Math.max(10, 12 / globalScale);
    ctx.font = `${fontSize}px ui-sans-serif, system-ui, -apple-system, Segoe UI`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillText(String(label), n.x || 0, (n.y || 0) + r + 3);
  };

  const zoomIn = () => {
    const cur = fgRef.current?.zoom() ?? 1;
    fgRef.current?.zoom(Math.min(6, cur * 1.25), 250);
  };
  const zoomOut = () => {
    const cur = fgRef.current?.zoom() ?? 1;
    fgRef.current?.zoom(Math.max(0.2, cur / 1.25), 250);
  };
  const reset = () => {
    fgRef.current?.zoomToFit(650, 80);
  };

  return (
    <div className="relative h-full">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <div className="text-sm font-semibold">Graph</div>
          <div className="text-xs text-white/60">Sales orders, items, materials, plants, and groups</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={zoomOut}
            className="rounded-lg border border-white/10 bg-black/30 p-2 text-white/80 transition hover:bg-black/45 hover:text-white"
            title="Zoom out"
          >
            <Minus size={16} />
          </button>
          <button
            onClick={zoomIn}
            className="rounded-lg border border-white/10 bg-black/30 p-2 text-white/80 transition hover:bg-black/45 hover:text-white"
            title="Zoom in"
          >
            <Plus size={16} />
          </button>
          <button
            onClick={reset}
            className="rounded-lg border border-white/10 bg-black/30 p-2 text-white/80 transition hover:bg-black/45 hover:text-white"
            title="Reset view"
          >
            <RotateCcw size={16} />
          </button>
        </div>
      </div>

      {loading && (
        <div className="absolute inset-0 z-10 grid place-items-center bg-card/70 backdrop-blur">
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white/80" />
            <div className="text-sm text-white/80">Loading graph…</div>
          </div>
        </div>
      )}

      <div className="h-[calc(100%-56px)]">
        {data && (
          <ForceGraph2D
            ref={fgRef as any}
            graphData={data as any}
            backgroundColor="#0F0F1A"
            linkColor={() => "rgba(255,255,255,0.12)"}
            linkWidth={1}
            linkDirectionalParticles={0}
            nodeCanvasObject={drawNode}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
              const n = node as GraphNode;
              const r = (NODE_SIZES[n.type] ?? 7) * 2;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(n.x || 0, n.y || 0, r, 0, 2 * Math.PI);
              ctx.fill();
            }}
            onNodeClick={(n: any) => onNodeClick(n as GraphNode)}
            onBackgroundClick={() => onNodeClick(null)}
            cooldownTicks={120}
            onEngineStop={() => fgRef.current?.zoomToFit(650, 80)}
          />
        )}
      </div>

      <div className="absolute bottom-3 left-3 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white/80 backdrop-blur">
        <div className="mb-1 text-[11px] font-semibold text-white/70">Legend</div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {LEGEND.map((l) => (
            <div key={l.type} className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />
              <span>{l.type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

