import React, { useMemo } from "react";
import { X } from "lucide-react";
import type { GraphNode } from "./GraphView";

type Props = {
  node: GraphNode | null;
  relatedNodes: GraphNode[];
  onClose: () => void;
};

const TYPE_STYLE: Record<
  string,
  { label: string; bg: string; text: string; border: string }
> = {
  SalesOrder: { label: "SalesOrder", bg: "bg-indigo-500/15", text: "text-indigo-200", border: "border-indigo-500/30" },
  SalesOrderItem: { label: "SalesOrderItem", bg: "bg-purple-500/15", text: "text-purple-200", border: "border-purple-500/30" },
  Material: { label: "Material", bg: "bg-emerald-500/15", text: "text-emerald-200", border: "border-emerald-500/30" },
  Plant: { label: "Plant", bg: "bg-amber-500/15", text: "text-amber-200", border: "border-amber-500/30" },
  MaterialGroup: { label: "MaterialGroup", bg: "bg-red-500/15", text: "text-red-200", border: "border-red-500/30" }
};

function fmt(v: unknown) {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function NodeInspector({ node, relatedNodes, onClose }: Props) {
  const open = !!node;
  const style = node ? TYPE_STYLE[node.type] : undefined;

  const rows = useMemo(() => {
    if (!node) return [];
    const d = node.data || {};
    const entries = Object.entries(d);
    entries.sort((a, b) => a[0].localeCompare(b[0]));
    return entries;
  }, [node]);

  return (
    <div
      className={[
        "fixed right-0 top-[73px] z-40 h-[calc(100%-73px)] w-[420px] max-w-[92vw]",
        "transform transition-transform duration-300 ease-out",
        open ? "translate-x-0" : "translate-x-full"
      ].join(" ")}
    >
      <div className="h-full border-l border-white/10 bg-card shadow-2xl">
        <div className="flex items-start justify-between border-b border-white/10 px-5 py-4">
          <div>
            <div className="text-sm font-semibold">Node Inspector</div>
            <div className="text-xs text-white/60">Details and neighbors</div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-white/10 bg-black/30 p-2 text-white/80 transition hover:bg-black/45 hover:text-white"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        {node ? (
          <div className="h-[calc(100%-65px)] overflow-auto px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="truncate text-base font-semibold">{node.label}</div>
                <div className="truncate text-xs text-white/60">{node.id}</div>
              </div>
              {style && (
                <span
                  className={[
                    "shrink-0 rounded-full border px-3 py-1 text-[11px] font-semibold",
                    style.bg,
                    style.text,
                    style.border
                  ].join(" ")}
                >
                  {style.label}
                </span>
              )}
            </div>

            <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="mb-3 text-[11px] font-semibold text-white/60">Properties</div>
              <table className="w-full text-xs">
                <tbody>
                  {rows.map(([k, v]) => (
                    <tr key={k} className="border-t border-white/5">
                      <td className="w-[42%] py-2 pr-3 align-top font-semibold text-white/70">
                        {k}
                      </td>
                      <td className="py-2 text-white/80">{fmt(v)}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td className="py-2 text-white/70">No properties available.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="mb-3 text-[11px] font-semibold text-white/60">Related Nodes</div>
              <div className="space-y-2">
                {relatedNodes.map((n) => (
                  <div
                    key={n.id}
                    className="flex items-center justify-between rounded-xl border border-white/10 bg-black/20 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-white/85">{n.label}</div>
                      <div className="truncate text-[11px] text-white/55">{n.type}</div>
                    </div>
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: n.color }} />
                  </div>
                ))}
                {relatedNodes.length === 0 && (
                  <div className="text-xs text-white/70">No related nodes in current view.</div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="grid h-[calc(100%-65px)] place-items-center px-6 text-center text-sm text-white/60">
            Click a node in the graph to inspect it.
          </div>
        )}
      </div>
    </div>
  );
}

