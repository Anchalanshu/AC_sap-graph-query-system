import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, SendHorizonal } from "lucide-react";
import type { GraphData, GraphNode, GraphLink } from "./GraphView";

export type ChatMessage = {
  id: string;
  role: "user" | "ai";
  content: string;
  sql?: string | null;
  explanation?: string;
  isDomainRelevant?: boolean;
  isGuardrail?: boolean;
};

type Props = {
  onHighlight: (nodeIds: string[]) => void;
  onGraph: (g: GraphData | null) => void;
  onError: (msg: string) => void;
  onAddMessage?: (m: ChatMessage) => void;
};

const SUGGESTED = [
  "Which material has highest total order value?",
  "Show orders with billing blocks",
  "Which plant produces the most items?",
  "List top 5 materials by quantity ordered",
  "Show rejected sales order items"
];

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

function historyForBackend(messages: ChatMessage[]) {
  // last 4 message pairs => last 8 messages max
  return messages.slice(-8).map((m) => ({
    role: m.role === "ai" ? "ai" : "user",
    content: m.content
  }));
}

function exportMarkdown(messages: ChatMessage[]) {
  const lines: string[] = [];
  lines.push("# Dodge AI — ERP Graph Explorer Chat Export");
  lines.push("");
  for (const m of messages) {
    lines.push(`## ${m.role === "user" ? "User" : "AI"}`);
    lines.push("");
    lines.push(m.content.trim() || "_(empty)_");
    lines.push("");
    if (m.role === "ai" && m.sql) {
      lines.push("### SQL");
      lines.push("");
      lines.push("```sql");
      lines.push(m.sql.trim());
      lines.push("```");
      lines.push("");
    }
    if (m.role === "ai" && m.explanation) {
      lines.push("### Explanation");
      lines.push("");
      lines.push(m.explanation.trim());
      lines.push("");
    }
  }
  return lines.join("\n");
}

export default function ChatPanel({ onHighlight, onGraph, onError, onAddMessage }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: "ai",
      content:
        "Ask about the SAP sales order items dataset (orders, materials, plants, billing blocks, rejections, quantities, amounts)."
    }
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [openSqlIds, setOpenSqlIds] = useState<Record<string, boolean>>({});
  const listRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, thinking, scrollToBottom]);

  const chips = useMemo(() => SUGGESTED, []);

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || thinking) return;

      const userMsg: ChatMessage = { id: uid(), role: "user", content: trimmed };
      setMessages((prev) => [...prev, userMsg]);
      onAddMessage?.(userMsg);
      setInput("");
      setThinking(true);

      const aiMsgId = uid();
      setMessages((prev) => [
        ...prev,
        { id: aiMsgId, role: "ai", content: "", sql: null, explanation: "" }
      ]);

      try {
        const resp = await fetch("/api/query/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream"
          },
          body: JSON.stringify({
            question: trimmed,
            history: historyForBackend([...messages, userMsg])
          })
        });

        if (!resp.ok || !resp.body) {
          const txt = await resp.text().catch(() => "");
          throw new Error(txt || `Request failed (${resp.status})`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        let meta: any = null;
        let finalPayload: any = null;

        const updateAi = (patch: Partial<ChatMessage>) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === aiMsgId ? { ...m, ...patch } : m))
          );
        };

        const graphFromPayload = (p: any): GraphData | null => {
          const g = p?.graph;
          if (!g || !Array.isArray(g.nodes) || !Array.isArray(g.edges)) return null;
          const nodes: GraphNode[] = g.nodes.map((n: any) => ({
            id: String(n.id),
            label: String(n.label ?? n.id),
            type: String(n.type),
            data: {}
          }));
          const links: GraphLink[] = g.edges.map((e: any) => ({
            source: String(e.source),
            target: String(e.target),
            label: String(e.label ?? "")
          }));
          return { nodes, links };
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const p of parts) {
            const line = p
              .split("\n")
              .map((l) => l.trim())
              .find((l) => l.startsWith("data:"));
            if (!line) continue;
            const jsonStr = line.replace(/^data:\s*/, "");
            let ev: any;
            try {
              ev = JSON.parse(jsonStr);
            } catch {
              continue;
            }

            if (ev.type === "error") {
              throw new Error(ev.error || "Streaming error");
            }

            if (ev.type === "meta") {
              meta = ev.payload;
              updateAi({
                sql: meta?.sql ?? null,
                explanation: meta?.explanation ?? "",
                isDomainRelevant: !!meta?.is_domain_relevant,
                isGuardrail: meta?.is_domain_relevant === false
              });
              const g = graphFromPayload(meta);
              if (g) onGraph(g);
              continue;
            }

            if (ev.type === "token") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId ? { ...m, content: (m.content || "") + (ev.token ?? "") } : m
                )
              );
              continue;
            }

            if (ev.type === "done") {
              finalPayload = ev.payload;
              updateAi({
                content: finalPayload?.answer ?? "",
                sql: finalPayload?.sql ?? null,
                explanation: finalPayload?.explanation ?? "",
                isDomainRelevant: !!finalPayload?.is_domain_relevant,
                isGuardrail: finalPayload?.is_domain_relevant === false
              });
              const ids = (finalPayload?.highlighted_nodes ?? []) as string[];
              if (Array.isArray(ids) && ids.length) onHighlight(ids);
              const g = graphFromPayload(finalPayload);
              if (g) onGraph(g);
              break;
            }
          }
        }

        // If backend didn’t send done, still try to highlight from meta
        if (!finalPayload && meta?.highlighted_nodes?.length) onHighlight(meta.highlighted_nodes);
      } catch (e: any) {
        const msg = e?.message || "Query failed";
        onError(msg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  content: msg,
                  isGuardrail: true,
                  isDomainRelevant: false
                }
              : m
          )
        );
      } finally {
        setThinking(false);
      }
    },
    [messages, onAddMessage, onError, onGraph, onHighlight, thinking]
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  const doExport = () => {
    const md = exportMarkdown(messages);
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dodge-ai-chat-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <div className="text-sm font-semibold">Chat</div>
          <div className="text-xs text-white/60">LLM generates SQL and explains results</div>
        </div>
        <button
          onClick={doExport}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-white/80 transition hover:bg-black/45 hover:text-white"
          title="Export chat as Markdown"
        >
          <Download size={16} />
          Export
        </button>
      </div>

      <div className="border-b border-white/10 px-4 py-3">
        <div className="mb-2 text-[11px] font-semibold text-white/60">Suggested queries</div>
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => (
            <button
              key={c}
              onClick={() => void send(c)}
              className="rounded-full border border-white/10 bg-black/20 px-3 py-1.5 text-xs text-white/80 transition hover:border-white/20 hover:bg-black/35 hover:text-white"
              disabled={thinking}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div ref={listRef} className="flex-1 space-y-3 overflow-auto px-4 py-4">
        {messages.map((m) => {
          const isUser = m.role === "user";
          const guard = !!m.isGuardrail;
          return (
            <div key={m.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div
                className={[
                  "max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
                  isUser
                    ? "bg-indigo-900/70 text-white"
                    : "bg-zinc-900/70 text-white border border-white/10",
                  guard && !isUser ? "border-orange-500/60 ring-1 ring-orange-500/20" : ""
                ].join(" ")}
              >
                <div className="whitespace-pre-wrap">
                  {m.content || (m.role === "ai" && thinking ? "" : "")}
                </div>

                {m.role === "ai" && !m.content && thinking && (
                  <div className="mt-1 inline-flex items-center gap-2 text-white/70">
                    <span className="text-xs">Thinking</span>
                    <span className="inline-flex gap-1">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:0ms]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:200ms]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:400ms]" />
                    </span>
                  </div>
                )}

                {m.role === "ai" && (m.sql || m.explanation) && (
                  <div className="mt-3 space-y-2">
                    {m.sql && (
                      <div>
                        <button
                          className="text-xs font-semibold text-white/70 transition hover:text-white"
                          onClick={() =>
                            setOpenSqlIds((s) => ({ ...s, [m.id]: !s[m.id] }))
                          }
                        >
                          {openSqlIds[m.id] ? "Hide SQL" : "Show SQL"}
                        </button>
                        {openSqlIds[m.id] && (
                          <pre className="mt-2 overflow-auto rounded-xl border border-white/10 bg-black/30 p-3 text-xs text-white/80">
                            <code>{m.sql}</code>
                          </pre>
                        )}
                      </div>
                    )}
                    {m.explanation && (
                      <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-white/75">
                        <div className="mb-1 text-[11px] font-semibold text-white/60">
                          Explanation
                        </div>
                        <div className="leading-relaxed">{m.explanation}</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <form onSubmit={onSubmit} className="border-t border-white/10 p-4">
        <div className="flex items-center gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about orders, materials, plants, billing blocks…"
            className="flex-1 rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-white/40 outline-none transition focus:border-white/20 focus:ring-2 focus:ring-indigo-500/25"
            disabled={thinking}
          />
          <button
            type="submit"
            disabled={thinking || !input.trim()}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <SendHorizonal size={16} />
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

