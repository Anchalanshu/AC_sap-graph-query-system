import React, { useCallback, useMemo, useState } from "react";
import GraphView, { GraphData, GraphNode } from "./components/GraphView";
import ChatPanel, { ChatMessage } from "./components/ChatPanel";
import NodeInspector from "./components/NodeInspector";

export default function App() {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [queryGraph, setQueryGraph] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  const onError = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 4500);
  }, []);

  const onHighlight = useCallback((ids: string[]) => {
    setHighlightedNodes(ids);
  }, []);

  const onGraphFromQuery = useCallback((g: GraphData | null) => {
    if (g && g.nodes?.length) setQueryGraph(g);
  }, []);

  const related = useMemo(() => {
    const active = queryGraph || graphData;
    if (!active || !selectedNode) return [];
    const neighbors = new Set<string>();
    for (const l of active.links) {
      const s = typeof l.source === "string" ? l.source : l.source.id;
      const t = typeof l.target === "string" ? l.target : l.target.id;
      if (s === selectedNode.id) neighbors.add(t);
      if (t === selectedNode.id) neighbors.add(s);
    }
    return active.nodes.filter((n) => neighbors.has(n.id));
  }, [graphData, queryGraph, selectedNode]);

  const onSelectNode = useCallback((n: GraphNode | null) => {
    setSelectedNode(n);
  }, []);

  const onGraphLoaded = useCallback((g: GraphData) => {
    setGraphData(g);
  }, []);

  const onChatAddMessage = useCallback((_m: ChatMessage) => {}, []);

  return (
    <div className="h-full bg-bg text-white">
      <header className="border-b border-white/10 bg-black/30 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4">
          <div>
            <div className="text-lg font-semibold tracking-wide">
              Dodge AI — ERP Graph Explorer
            </div>
            <div className="text-sm text-white/60">
              Graph-based SAP Sales Order Items modeling + LLM-assisted querying
            </div>
          </div>
          <div className="text-xs text-white/60">
            Backend: FastAPI • Graph: NetworkX • UI: React
          </div>
        </div>
      </header>

      <main className="mx-auto grid h-[calc(100%-73px)] max-w-[1400px] grid-cols-10 gap-4 px-6 py-4">
        <section className="col-span-6 overflow-hidden rounded-2xl border border-white/10 bg-card shadow-[0_0_0_1px_rgba(255,255,255,0.04)]">
          <GraphView
            graphOverride={queryGraph}
            onLoaded={onGraphLoaded}
            onNodeClick={onSelectNode}
            highlightedNodeIds={highlightedNodes}
            onError={onError}
          />
        </section>
        <section className="col-span-4 overflow-hidden rounded-2xl border border-white/10 bg-card shadow-[0_0_0_1px_rgba(255,255,255,0.04)]">
          <ChatPanel
            onHighlight={onHighlight}
            onGraph={onGraphFromQuery}
            onError={onError}
            onAddMessage={onChatAddMessage}
          />
        </section>

        <NodeInspector
          node={selectedNode}
          relatedNodes={related}
          onClose={() => setSelectedNode(null)}
        />

        {toast && (
          <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2">
            <div className="rounded-xl border border-white/15 bg-black/60 px-4 py-3 text-sm text-white shadow-lg backdrop-blur">
              {toast}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

