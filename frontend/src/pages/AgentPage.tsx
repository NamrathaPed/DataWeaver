import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Plot from "react-plotly.js";
import { runAgentAnalysis, type AgentEvent, type PlotlyFigure } from "@/services/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TimelineItem =
  | { kind: "thinking"; text: string }
  | { kind: "tool_call"; tool: string; args: Record<string, unknown>; result?: string }
  | { kind: "finding"; headline: string; detail: string; stat?: string }
  | { kind: "chart"; figure: PlotlyFigure; title: string }
  | { kind: "report"; markdown: string }
  | { kind: "error"; message: string };

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AgentPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const [problem, setProblem] = useState("");
  const [phase, setPhase] = useState<"input" | "running" | "done">("input");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [followUp, setFollowUp] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<(() => void) | null>(null);

  if (!sessionId) { navigate("/"); return null; }

  // Auto-scroll to bottom as events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline]);

  const handleEvent = useCallback((event: AgentEvent) => {
    setTimeline((prev) => {
      switch (event.type) {
        case "thinking":
          // Merge consecutive thinking blocks
          if (prev.length > 0 && prev[prev.length - 1].kind === "thinking") {
            const updated = [...prev];
            const last = updated[updated.length - 1] as { kind: "thinking"; text: string };
            updated[updated.length - 1] = { ...last, text: last.text + "\n" + event.text };
            return updated;
          }
          return [...prev, { kind: "thinking", text: event.text }];

        case "tool_call":
          return [...prev, { kind: "tool_call", tool: event.tool, args: event.args }];

        case "tool_result": {
          // Attach result summary to the last matching tool_call
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].kind === "tool_call" && (updated[i] as { tool: string }).tool === event.tool && !(updated[i] as { result?: string }).result) {
              updated[i] = { ...(updated[i] as object), result: event.summary } as TimelineItem;
              return updated;
            }
          }
          return prev;
        }

        case "finding":
          return [...prev, { kind: "finding", headline: event.headline, detail: event.detail, stat: event.stat }];

        case "chart":
          return [...prev, { kind: "chart", figure: event.figure, title: event.title }];

        case "report":
          return [...prev, { kind: "report", markdown: event.markdown }];

        case "error":
          return [...prev, { kind: "error", message: event.message }];

        case "done":
          setPhase("done");
          return prev;

        default:
          return prev;
      }
    });
  }, []);

  const startAnalysis = useCallback((userProblem: string) => {
    if (!userProblem.trim() || !sessionId) return;
    setTimeline([]);
    setPhase("running");

    const stop = runAgentAnalysis(
      sessionId,
      userProblem,
      handleEvent,
      (err) => {
        setTimeline((prev) => [...prev, { kind: "error", message: err.message }]);
        setPhase("done");
      }
    );
    stopRef.current = stop;
  }, [sessionId, handleEvent]);

  const handleFollowUp = useCallback(() => {
    if (!followUp.trim()) return;
    const question = followUp.trim();
    setFollowUp("");
    // Append the follow-up as a new user question marker + restart agent
    setTimeline((prev) => [
      ...prev,
      { kind: "thinking", text: `Follow-up: ${question}` },
    ]);
    startAnalysis(question);
  }, [followUp, startAnalysis]);

  // Cleanup on unmount
  useEffect(() => () => stopRef.current?.(), []);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => navigate("/")}
            className="text-xl font-bold text-gray-900 tracking-tight"
          >
            Data<span className="text-brand-500">Weaver</span>
          </button>
          <div className="flex items-center gap-3">
            {phase === "running" && (
              <span className="flex items-center gap-2 text-sm text-brand-600 font-medium">
                <PulsingDot />
                Analysing…
              </span>
            )}
            {phase === "done" && (
              <span className="text-sm text-green-600 font-medium">Analysis complete</span>
            )}
            <button
              onClick={() => navigate(`/dashboard/${sessionId}`)}
              className="text-sm text-gray-400 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Classic view →
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <div className="flex-1 max-w-4xl mx-auto w-full px-6 py-10 flex flex-col gap-8">

        {/* Problem input (shown before analysis starts) */}
        {phase === "input" && (
          <div className="flex flex-col gap-6">
            <div className="text-center space-y-2">
              <h2 className="text-2xl font-bold text-gray-900">What do you want to understand?</h2>
              <p className="text-gray-500 max-w-xl mx-auto">
                Describe your analysis problem in plain language. DataWeaver will plan the
                investigation, run the analysis, and write a full report.
              </p>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
              <textarea
                value={problem}
                onChange={(e) => setProblem(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) startAnalysis(problem);
                }}
                placeholder={
                  'e.g. "I have crash data from Chicago. Find what\'s causing the most injuries."\n' +
                  'e.g. "Analyse sales data to find which products are underperforming and why."'
                }
                rows={4}
                className="w-full resize-none text-gray-800 placeholder-gray-300 text-base focus:outline-none"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-300">⌘ + Enter to run</span>
                <button
                  disabled={!problem.trim()}
                  onClick={() => startAnalysis(problem)}
                  className="px-5 py-2.5 bg-brand-500 text-white text-sm font-semibold rounded-xl hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Start Analysis →
                </button>
              </div>
            </div>

            <ExamplePrompts onSelect={(p) => { setProblem(p); startAnalysis(p); }} />
          </div>
        )}

        {/* Problem statement banner (shown while running / done) */}
        {(phase === "running" || phase === "done") && (
          <div className="bg-brand-50 border border-brand-100 rounded-2xl px-6 py-4">
            <p className="text-xs font-semibold text-brand-400 uppercase tracking-wider mb-1">Analysis problem</p>
            <p className="text-gray-800 font-medium">{problem}</p>
          </div>
        )}

        {/* Timeline */}
        {timeline.length > 0 && (
          <div className="flex flex-col gap-4">
            {timeline.map((item, i) => (
              <TimelineEntry key={i} item={item} />
            ))}
            {phase === "running" && <ThinkingIndicator />}
          </div>
        )}

        {/* Follow-up input */}
        {phase === "done" && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 flex gap-3">
            <input
              value={followUp}
              onChange={(e) => setFollowUp(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleFollowUp()}
              placeholder="Ask a follow-up question…"
              className="flex-1 text-sm text-gray-800 placeholder-gray-400 focus:outline-none"
            />
            <button
              disabled={!followUp.trim()}
              onClick={handleFollowUp}
              className="px-4 py-2 bg-brand-500 text-white text-sm font-semibold rounded-xl hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Ask
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline entry renderer
// ---------------------------------------------------------------------------

function TimelineEntry({ item }: { item: TimelineItem }) {
  switch (item.kind) {
    case "thinking":
      return <ThinkingBlock text={item.text} />;
    case "tool_call":
      return <ToolCallBlock tool={item.tool} args={item.args} result={item.result} />;
    case "finding":
      return <FindingCard headline={item.headline} detail={item.detail} stat={item.stat} />;
    case "chart":
      return <ChartBlock figure={item.figure} title={item.title} />;
    case "report":
      return <ReportBlock markdown={item.markdown} />;
    case "error":
      return (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-red-700 text-sm">
          {item.message}
        </div>
      );
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ThinkingBlock({ text }: { text: string }) {
  return (
    <div className="flex gap-3 items-start">
      <div className="mt-1 w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
        <BrainIcon />
      </div>
      <p className="text-sm text-gray-500 leading-relaxed whitespace-pre-wrap">{text}</p>
    </div>
  );
}

function ToolCallBlock({
  tool,
  args,
  result,
}: {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const label = TOOL_LABELS[tool] ?? tool;

  return (
    <div className="flex gap-3 items-start">
      <div className="mt-0.5 w-5 h-5 rounded-full bg-brand-50 flex items-center justify-center shrink-0">
        <WrenchIcon />
      </div>
      <div className="flex-1 min-w-0">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 text-sm font-medium text-brand-700 hover:text-brand-900 transition-colors"
        >
          <span>{label}</span>
          <ChevronIcon expanded={expanded} />
        </button>
        {result && (
          <p className="text-xs text-gray-400 mt-0.5 truncate">{result}</p>
        )}
        {expanded && (
          <pre className="mt-2 text-xs bg-gray-50 rounded-lg p-3 overflow-x-auto text-gray-600 border border-gray-100">
            {JSON.stringify(args, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function FindingCard({
  headline,
  detail,
  stat,
}: {
  headline: string;
  detail: string;
  stat?: string;
}) {
  return (
    <div className="bg-white border border-brand-100 rounded-2xl p-5 shadow-sm">
      <div className="flex items-start gap-4">
        <div className="mt-0.5 w-8 h-8 rounded-xl bg-brand-50 flex items-center justify-center shrink-0">
          <LightbulbIcon />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900">{headline}</p>
          {stat && (
            <p className="text-2xl font-bold text-brand-600 mt-1">{stat}</p>
          )}
          <p className="text-sm text-gray-500 mt-2 leading-relaxed">{detail}</p>
        </div>
      </div>
    </div>
  );
}

function ChartBlock({ figure, title }: { figure: PlotlyFigure; title: string }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <Plot
        data={figure.data as Plotly.Data[]}
        layout={{
          ...(figure.layout as Partial<Plotly.Layout>),
          autosize: true,
          margin: { t: 48, r: 24, b: 48, l: 48 },
          font: { family: "Inter, sans-serif", size: 12 },
          paper_bgcolor: "white",
          plot_bgcolor: "#f9fafb",
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height: 380 }}
        useResizeHandler
      />
      <p className="px-5 pb-4 text-xs text-gray-400 text-center">{title}</p>
    </div>
  );
}

function ReportBlock({ markdown }: { markdown: string }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-8">
      <div className="flex items-center gap-2 mb-6 pb-4 border-b border-gray-100">
        <DocumentIcon />
        <h3 className="font-semibold text-gray-900">Analysis Report</h3>
      </div>
      <div className="prose prose-sm max-w-none text-gray-700 leading-relaxed">
        <SimpleMarkdown text={markdown} />
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex gap-3 items-center">
      <div className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
        <PulsingDot />
      </div>
      <span className="text-sm text-gray-400">Working…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Simple markdown renderer (handles ##, **, -, plain text)
// ---------------------------------------------------------------------------

function SimpleMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("### ")) {
      elements.push(<h3 key={i} className="text-base font-semibold text-gray-900 mt-5 mb-2">{line.slice(4)}</h3>);
    } else if (line.startsWith("## ")) {
      elements.push(<h2 key={i} className="text-lg font-bold text-gray-900 mt-6 mb-3">{line.slice(3)}</h2>);
    } else if (line.startsWith("# ")) {
      elements.push(<h1 key={i} className="text-xl font-bold text-gray-900 mt-6 mb-3">{line.slice(2)}</h1>);
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <li key={i} className="ml-4 list-disc text-gray-700 text-sm">
          <InlineMd text={line.slice(2)} />
        </li>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-2" />);
    } else {
      elements.push(
        <p key={i} className="text-sm text-gray-700 leading-relaxed">
          <InlineMd text={line} />
        </p>
      );
    }
    i++;
  }

  return <>{elements}</>;
}

function InlineMd({ text }: { text: string }) {
  // Handle **bold**
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold text-gray-900">{part.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Example prompts
// ---------------------------------------------------------------------------

const EXAMPLES = [
  "Find the leading causes of injuries in this dataset",
  "Which time periods show the highest incident rates?",
  "What factors are most correlated with the outcome?",
  "Identify the top patterns and anomalies in this data",
];

function ExamplePrompts({ onSelect }: { onSelect: (p: string) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Example prompts</p>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => onSelect(ex)}
            className="text-sm px-3 py-1.5 rounded-lg bg-white border border-gray-200 text-gray-600 hover:border-brand-300 hover:text-brand-700 transition-colors"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tool label map
// ---------------------------------------------------------------------------

const TOOL_LABELS: Record<string, string> = {
  get_dataset_overview: "Reading dataset overview",
  get_column_stats: "Getting column statistics",
  get_value_distribution: "Computing value distribution",
  filter_and_group: "Grouping and aggregating data",
  run_correlation: "Computing correlation",
  generate_chart: "Generating chart",
  write_finding: "Recording finding",
};

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function PulsingDot() {
  return (
    <span className="inline-block w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
  );
}

function BrainIcon() {
  return (
    <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  );
}

function WrenchIcon() {
  return (
    <svg className="w-3 h-3 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
    </svg>
  );
}

function LightbulbIcon() {
  return (
    <svg className="w-4 h-4 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`w-3 h-3 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}
