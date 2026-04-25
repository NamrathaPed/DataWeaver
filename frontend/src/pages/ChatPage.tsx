/**
 * ChatPage — main application page.
 * Layout: collapsible left sidebar (Reports, Chats, View) + centred chat area.
 * All agent/upload/streaming logic is preserved from the original.
 */

import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type RefObject,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import Plot from "react-plotly.js";

import {
  uploadFile,
  analyzeDataset,
  selectSheet,
  runAgentAnalysis,
  fetchAllSessions,
  type PlotlyFigure,
  type AgentEvent,
} from "@/services/api";
import { useTheme } from "@/hooks/useTheme";

// ─────────────────────────────────────────────────────────────────────────────
// localStorage types
// ─────────────────────────────────────────────────────────────────────────────

interface StoredSession {
  sessionId: string;
  filename: string;
  rows: number;
  cols: number;
  createdAt: string;
}

interface StoredReport {
  id: string;
  sessionId: string;
  filename: string;
  markdown: string;
  title: string;
  createdAt: string;
}

const LS_SESSIONS = "dw_sessions";
const LS_REPORTS  = "dw_reports";
const LS_MSGS_PFX = "dw_msgs_"; // per-session message key

function loadSessions(): StoredSession[] {
  try { return JSON.parse(localStorage.getItem(LS_SESSIONS) ?? "[]"); }
  catch { return []; }
}

function saveSessions(sessions: StoredSession[]) {
  localStorage.setItem(LS_SESSIONS, JSON.stringify(sessions.slice(0, 20)));
}

function loadReports(): StoredReport[] {
  try { return JSON.parse(localStorage.getItem(LS_REPORTS) ?? "[]"); }
  catch { return []; }
}

function saveReports(reports: StoredReport[]) {
  localStorage.setItem(LS_REPORTS, JSON.stringify(reports.slice(0, 50)));
}

/** Persist messages for a session.
 *  Chart figures are stripped before saving — each Plotly JSON can be 200KB+,
 *  which silently blows the 5MB localStorage quota and wipes everything.
 *  A placeholder is stored instead; ChartCard renders a "regenerate" prompt.
 */
function saveMessages(sessionId: string, msgs: ChatMsg[]) {
  const stable = msgs.filter((m) => m.role !== "assistant" || !m.streaming);
  const lightweight = stable.map((m): ChatMsg => {
    if (m.role !== "assistant") return m;
    return {
      ...m,
      items: m.items.map((item) =>
        item.kind === "chart"
          ? { ...item, figure: { data: [], layout: {} } }
          : item
      ),
    };
  });
  try {
    localStorage.setItem(LS_MSGS_PFX + sessionId, JSON.stringify(lightweight));
  } catch {
    // Still too large (many messages) — skip silently
  }
}

function loadMessages(sessionId: string): ChatMsg[] {
  try { return JSON.parse(localStorage.getItem(LS_MSGS_PFX + sessionId) ?? "[]"); }
  catch { return []; }
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat / agent types
// ─────────────────────────────────────────────────────────────────────────────

type Phase = "welcome" | "uploading" | "ready" | "running" | "done";

interface SessionInfo {
  sessionId: string;
  filename: string;
  rows: number;
  cols: number;
}

type AssistantItem =
  | { kind: "tool";    name: string; label: string; result?: string }
  | { kind: "finding"; headline: string; detail: string; stat?: string }
  | { kind: "chart";   figure: PlotlyFigure; title: string }
  | { kind: "report";  markdown: string }
  | { kind: "error";   message: string };

type ChatMsg =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "file"; filename: string; rows: number; cols: number; status: "loading" | "ready" | "error"; error?: string }
  | { id: string; role: "assistant"; items: AssistantItem[]; streaming: boolean };

// ─────────────────────────────────────────────────────────────────────────────
// Pure message helpers
// ─────────────────────────────────────────────────────────────────────────────

function appendItem(msgs: ChatMsg[], aid: string, item: AssistantItem): ChatMsg[] {
  return msgs.map((m) =>
    m.id === aid && m.role === "assistant" ? { ...m, items: [...m.items, item] } : m
  );
}

function markResult(msgs: ChatMsg[], aid: string, tool: string, result: string): ChatMsg[] {
  return msgs.map((m) => {
    if (m.id !== aid || m.role !== "assistant") return m;
    const items = [...m.items];
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      if (it.kind === "tool" && it.name === tool && !it.result) {
        items[i] = { ...it, result };
        break;
      }
    }
    return { ...m, items };
  });
}

function stopStream(msgs: ChatMsg[], aid: string): ChatMsg[] {
  return msgs.map((m) =>
    m.id === aid && m.role === "assistant" ? { ...m, streaming: false } : m
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tool label map
// ─────────────────────────────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  get_dataset_overview:    "Reading dataset overview",
  get_column_stats:        "Fetching column statistics",
  get_value_distribution:  "Computing value distribution",
  filter_and_group:        "Grouping & aggregating data",
  run_correlation:         "Running correlation analysis",
  run_linear_regression:   "Running linear regression",
  generate_chart:          "Generating chart",
  write_finding:           "Recording finding",
};

// ─────────────────────────────────────────────────────────────────────────────
// Page component
// ─────────────────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const navigate = useNavigate();
  const { sessionId: urlSessionId } = useParams<{ sessionId: string }>();
  const { theme, toggle: toggleTheme } = useTheme();

  // ── Core chat state ────────────────────────────────────────────────────────
  const [phase,       setPhase]       = useState<Phase>(urlSessionId ? "ready" : "welcome");
  const [session,     setSession]     = useState<SessionInfo | null>(null);
  const [messages,    setMessages]    = useState<ChatMsg[]>(
    () => urlSessionId ? loadMessages(urlSessionId) : []
  );
  const [input,       setInput]       = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [sheetOptions,setSheetOptions]= useState<{ file: File; sheets: string[] } | null>(null);

  // ── Sidebar state ─────────────────────────────────────────────────────────
  const [sidebarOpen,    setSidebarOpen]    = useState(true);
  const [reportsOpen,    setReportsOpen]    = useState(true);
  const [chatsOpen,      setChatsOpen]      = useState(true);
  const [sessions,       setSessions]       = useState<StoredSession[]>(loadSessions);
  const [reports,        setReports]        = useState<StoredReport[]>(loadReports);

  // ── Restore session from localStorage when navigating back to /chat/:id ─────
  // session state is lost on navigation; messages survive via localStorage
  useEffect(() => {
    if (!urlSessionId || session) return;
    const stored = sessions.find((s) => s.sessionId === urlSessionId);
    if (stored) {
      setSession({ sessionId: stored.sessionId, filename: stored.filename, rows: stored.rows, cols: stored.cols });
      setPhase("ready");
    }
  }, [urlSessionId, session, sessions]);

  // ── Load sessions from Supabase on mount (merge with localStorage) ─────────
  useEffect(() => {
    fetchAllSessions().then((remote) => {
      if (!remote.length) return;
      const remapped: StoredSession[] = remote.map((s) => ({
        sessionId:  s.session_id,
        filename:   s.filename,
        rows:       s.row_count,
        cols:       s.col_count,
        createdAt:  s.created_at,
      }));
      setSessions((local) => {
        // Merge: remote is authoritative, keep any local-only entries
        const remoteIds = new Set(remapped.map((s) => s.sessionId));
        const localOnly = local.filter((s) => !remoteIds.has(s.sessionId));
        const merged = [...remapped, ...localOnly];
        saveSessions(merged);
        return merged;
      });
    }).catch(() => { /* Supabase not configured — stay with localStorage */ });
  }, []);

  // ── Refs ──────────────────────────────────────────────────────────────────
  const fileInputRef  = useRef<HTMLInputElement>(null);
  const textareaRef   = useRef<HTMLTextAreaElement>(null);
  const bottomRef     = useRef<HTMLDivElement>(null);
  const stopAgentRef  = useRef<(() => void) | null>(null);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // ── Persist messages to localStorage whenever they settle ─────────────────
  useEffect(() => {
    const sid = session?.sessionId ?? urlSessionId;
    if (!sid || messages.length === 0) return;
    // Debounce: only save when no message is actively streaming
    const isStreaming = messages.some((m) => m.role === "assistant" && m.streaming);
    if (!isStreaming) saveMessages(sid, messages);
  }, [messages, session, urlSessionId]);

  // ── Cleanup agent on unmount ──────────────────────────────────────────────
  useEffect(() => () => { stopAgentRef.current?.(); }, []);

  // ── Agent event handler ───────────────────────────────────────────────────
  const handleAgentEvent = useCallback(
    (aid: string, event: AgentEvent, localSetPhase: (p: Phase) => void) => {
      switch (event.type) {
        case "thinking": break;
        case "tool_call":
          setMessages((p) => appendItem(p, aid, { kind: "tool", name: event.tool, label: TOOL_LABELS[event.tool] ?? event.tool }));
          break;
        case "tool_result":
          setMessages((p) => markResult(p, aid, event.tool, event.summary));
          break;
        case "finding":
          setMessages((p) => appendItem(p, aid, { kind: "finding", headline: event.headline, detail: event.detail, stat: event.stat }));
          break;
        case "chart":
          setMessages((p) => appendItem(p, aid, { kind: "chart", figure: event.figure, title: event.title }));
          break;
        case "report":
          setMessages((p) => appendItem(p, aid, { kind: "report", markdown: event.markdown }));
          // Persist report to localStorage
          setReports((prev) => {
            const updated = [
              {
                id: `r-${Date.now()}`,
                sessionId: session?.sessionId ?? "",
                filename: session?.filename ?? "Unknown",
                markdown: event.markdown,
                title: session?.filename ? `Analysis — ${session.filename}` : "Analysis Report",
                createdAt: new Date().toISOString(),
              },
              ...prev,
            ];
            saveReports(updated);
            return updated;
          });
          break;
        case "error":
          setMessages((p) => appendItem(p, aid, { kind: "error", message: event.message }));
          setMessages((p) => stopStream(p, aid));
          localSetPhase("done");
          break;
        case "done":
          setMessages((p) => stopStream(p, aid));
          localSetPhase("done");
          break;
      }
    },
    [session]
  );

  // ── Build compact history for the agent (user messages + assistant summaries) ──
  const buildHistory = useCallback((msgs: ChatMsg[]): { role: string; content: string }[] => {
    const result: { role: string; content: string }[] = [];
    for (const m of msgs) {
      if (m.role === "user") {
        result.push({ role: "user", content: m.text });
      } else if (m.role === "assistant" && !m.streaming) {
        const content = m.items
          .filter((i) => i.kind === "report" || i.kind === "finding")
          .map((i) => i.kind === "report" ? i.markdown.slice(0, 400) : `${i.headline}: ${i.detail}`)
          .join("\n");
        if (content) result.push({ role: "assistant", content });
      }
    }
    return result.slice(-8); // last 8 turns keeps context tight
  }, []);

  // ── Ref that always holds the latest messages (avoids stale closure in runAgent) ──
  const messagesRef = useRef<ChatMsg[]>(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  // ── Run agent ─────────────────────────────────────────────────────────────
  const runAgent = useCallback(
    (sessionId: string, prompt: string) => {
      const aid = `a-${Date.now()}`;
      const history = buildHistory(messagesRef.current);

      setMessages((p) => [...p, { id: aid, role: "assistant" as const, items: [], streaming: true }]);
      setPhase("running");

      const stop = runAgentAnalysis(
        sessionId,
        prompt,
        (event) => handleAgentEvent(aid, event, setPhase),
        (err) => {
          setMessages((p) => appendItem(p, aid, { kind: "error", message: err.message }));
          setMessages((p) => stopStream(p, aid));
          setPhase("done");
        },
        history,
      );
      stopAgentRef.current = stop;
      return aid;
    },
    [handleAgentEvent, buildHistory]
  );

  // ── Upload flow ───────────────────────────────────────────────────────────
  const processFile = useCallback(
    async (file: File, sheetName?: string) => {
      const fid = `f-${Date.now()}`;
      setMessages((p) => [...p, { id: fid, role: "file", filename: file.name, rows: 0, cols: 0, status: "loading" }]);
      setPhase("uploading");

      try {
        const res = sheetName ? await selectSheet(file, sheetName) : await uploadFile(file);

        if (res.requires_sheet_selection && res.sheets) {
          setSheetOptions({ file, sheets: res.sheets });
          setMessages((p) => p.filter((m) => m.id !== fid));
          setPhase("welcome");
          return;
        }

        await analyzeDataset(res.session_id);

        const info: SessionInfo = { sessionId: res.session_id, filename: res.filename, rows: res.row_count, cols: res.col_count };
        setSession(info);

        setMessages((p) =>
          p.map((m) =>
            m.id === fid
              ? ({ ...m, status: "ready", rows: res.row_count, cols: res.col_count } as ChatMsg)
              : m
          )
        );

        navigate(`/chat/${res.session_id}`, { replace: true });
        setPhase("ready");

        // Persist session to localStorage
        setSessions((prev) => {
          const filtered = prev.filter((s) => s.sessionId !== res.session_id);
          const updated  = [{ sessionId: res.session_id, filename: res.filename, rows: res.row_count, cols: res.col_count, createdAt: new Date().toISOString() }, ...filtered];
          saveSessions(updated);
          return updated;
        });

        // Auto-run intro
        runAgent(
          res.session_id,
          `I've just uploaded "${res.filename}" (${res.row_count.toLocaleString()} rows, ${res.col_count} columns). ` +
          `Give me a brief, friendly introduction to this dataset — what it contains, 2-3 most notable patterns or stats you can already see, ` +
          `and then ask me one focused question about what I'd like to analyse. Keep it conversational and under 150 words. No markdown headers.`
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Upload failed.";
        setMessages((p) => p.map((m) => m.id === fid ? ({ ...m, status: "error", error: msg } as ChatMsg) : m));
        setPhase("welcome");
      }
    },
    [navigate, runAgent]
  );

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(() => {
    if (phase === "uploading" || phase === "running") return;
    if (pendingFile) {
      const file = pendingFile;
      setPendingFile(null);
      setInput("");
      processFile(file);
      return;
    }
    const text = input.trim();
    if (!text || !session) return;
    setMessages((p) => [...p, { id: `u-${Date.now()}`, role: "user", text }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    runAgent(session.sessionId, text);
  }, [phase, pendingFile, input, session, processFile, runAgent]);

  // ── Dropzone ──────────────────────────────────────────────────────────────
  const onDrop = useCallback((files: File[]) => { if (files[0]) processFile(files[0]); }, [processFile]);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
    },
    noClick: true,
    disabled: phase === "uploading" || phase === "running",
  });

  // ── Open session from sidebar ─────────────────────────────────────────────
  const openSession = (s: StoredSession) => {
    navigate(`/chat/${s.sessionId}`);
    setMessages(loadMessages(s.sessionId));
    setPhase("ready");
    setSession({ sessionId: s.sessionId, filename: s.filename, rows: s.rows, cols: s.cols });
    setInput("");
  };

  return (
    <div
      {...getRootProps()}
      className="h-screen flex flex-col bg-[var(--bg-base)] relative overflow-hidden"
    >
      <input {...getInputProps()} />

      {/* ── Drag overlay ──────────────────────────────────────────────────── */}
      {isDragActive && (
        <div className="absolute inset-0 z-50 pointer-events-none flex items-center justify-center bg-brand-500/10 border-2 border-dashed border-brand-500">
          <div className="text-center space-y-2">
            <div className="text-5xl">📂</div>
            <p className="font-semibold text-brand-600 dark:text-brand-400 text-lg">Drop to upload</p>
            <p className="text-sm text-brand-500/70">CSV, XLSX, XLS</p>
          </div>
        </div>
      )}

      {/* ── Sheet picker modal ─────────────────────────────────────────────── */}
      {sheetOptions && (
        <SheetPicker
          sheets={sheetOptions.sheets}
          onPick={(sheet) => { const f = sheetOptions.file; setSheetOptions(null); processFile(f, sheet); }}
          onDismiss={() => setSheetOptions(null)}
        />
      )}

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="shrink-0 h-14 flex items-center justify-between px-4 border-b border-[var(--border)] bg-[var(--bg-surface)] z-20">
        <div className="flex items-center gap-3">
          {/* Sidebar toggle (header level) */}
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            <SidebarToggleIcon open={sidebarOpen} />
          </button>
          <button
            onClick={() => navigate("/")}
            className="text-lg font-bold tracking-tight text-[var(--text-primary)]"
          >
            Data<span className="text-brand-500">Weaver</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          {session && (
            <span className="hidden sm:inline text-xs text-[var(--text-muted)] bg-[var(--bg-elevated)] px-2.5 py-1 rounded-full border border-[var(--border)]">
              {session.filename} · {session.rows.toLocaleString()} rows
            </span>
          )}
          <ThemeToggle theme={theme} toggle={toggleTheme} />
        </div>
      </header>

      {/* ── Body (sidebar + main) ──────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <aside
          className={`shrink-0 flex flex-col border-r border-[var(--border)] bg-[var(--bg-surface)] transition-all duration-200 ease-in-out overflow-hidden ${
            sidebarOpen ? "w-64" : "w-14"
          }`}
        >
          {sidebarOpen ? (
            /* ── Expanded sidebar ─────────────────────────────────────────── */
            <div className="flex flex-col h-full overflow-hidden">

              {/* Reports section */}
              <SidebarSection
                label="Reports"
                icon={<ReportsIcon />}
                open={reportsOpen}
                onToggle={() => setReportsOpen((o) => !o)}
                count={reports.length}
              >
                {reports.length === 0 ? (
                  <p className="text-xs text-[var(--text-muted)] px-3 py-2 italic">
                    No reports yet. Ask the AI to analyse your data and a report will appear here.
                  </p>
                ) : (
                  reports.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => navigate(`/dashboard/${r.sessionId}`)}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--bg-elevated)] group transition-colors"
                    >
                      <p className="text-xs font-medium text-[var(--text-primary)] truncate group-hover:text-brand-500 transition-colors">
                        {r.title}
                      </p>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">
                        {formatDate(r.createdAt)}
                      </p>
                    </button>
                  ))
                )}
              </SidebarSection>

              {/* Chats section */}
              <SidebarSection
                label="Chats"
                icon={<ChatsIcon />}
                open={chatsOpen}
                onToggle={() => setChatsOpen((o) => !o)}
                count={sessions.length}
                extra={
                  <button
                    onClick={() => navigate("/chat")}
                    className="w-5 h-5 rounded flex items-center justify-center text-[var(--text-muted)] hover:text-brand-500 hover:bg-brand-500/10 transition-colors"
                    title="New chat"
                  >
                    <NewChatIcon />
                  </button>
                }
              >
                {sessions.length === 0 ? (
                  <p className="text-xs text-[var(--text-muted)] px-3 py-2 italic">
                    No chats yet. Upload a file to start.
                  </p>
                ) : (
                  sessions.map((s) => (
                    <button
                      key={s.sessionId}
                      onClick={() => openSession(s)}
                      className={`w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--bg-elevated)] group transition-colors ${
                        session?.sessionId === s.sessionId ? "bg-brand-500/8 border border-brand-500/20" : ""
                      }`}
                    >
                      <p className={`text-xs font-medium truncate transition-colors ${
                        session?.sessionId === s.sessionId
                          ? "text-brand-500"
                          : "text-[var(--text-primary)] group-hover:text-brand-500"
                      }`}>
                        {s.filename}
                      </p>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">
                        {s.rows.toLocaleString()} rows · {formatDate(s.createdAt)}
                      </p>
                    </button>
                  ))
                )}
              </SidebarSection>

              {/* View section */}
              <div className="border-t border-[var(--border)] mt-auto">
                <div className="px-3 py-3">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 px-1">
                    View
                  </p>
                  {session ? (
                    <button
                      onClick={() => navigate(`/dashboard/${session.sessionId}`)}
                      className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-brand-500/10 border border-brand-500/20 text-brand-600 dark:text-brand-400 text-xs font-medium hover:bg-brand-500/15 transition-colors"
                    >
                      <ViewIcon />
                      <span>Open full analysis view</span>
                      <svg className="w-3 h-3 ml-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                    </button>
                  ) : (
                    <p className="text-xs text-[var(--text-muted)] italic px-1">
                      Upload a file to access the analysis view.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* ── Collapsed sidebar (icon strip) ───────────────────────────── */
            <div className="flex flex-col items-center py-3 gap-1">
              <SidebarIconBtn
                title="Reports"
                icon={<ReportsIcon />}
                badge={reports.length}
                onClick={() => setSidebarOpen(true)}
              />
              <SidebarIconBtn
                title="Chats"
                icon={<ChatsIcon />}
                badge={sessions.length}
                onClick={() => setSidebarOpen(true)}
              />
              {session && (
                <SidebarIconBtn
                  title="Full analysis view"
                  icon={<ViewIcon />}
                  onClick={() => navigate(`/dashboard/${session.sessionId}`)}
                />
              )}
              <div className="mt-auto mb-1">
                <SidebarIconBtn
                  title="New chat"
                  icon={<NewChatIcon />}
                  onClick={() => navigate("/chat")}
                />
              </div>
            </div>
          )}
        </aside>

        {/* ── Main chat area ─────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0">
          {phase === "welcome" && messages.length === 0 ? (
            /* ── Welcome / empty state ────────────────────────────────────── */
            <WelcomeState
              fileInputRef={fileInputRef}
              pendingFile={pendingFile}
              setPendingFile={setPendingFile}
              processFile={processFile}
              input={input}
              setInput={setInput}
              textareaRef={textareaRef}
              onSend={sendMessage}
            />
          ) : (
            /* ── Active chat ──────────────────────────────────────────────── */
            <>
              <div className="flex-1 overflow-y-auto">
                <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-4">
                  {messages.map((msg) => (
                    <MessageRow key={msg.id} msg={msg} />
                  ))}
                  {phase === "running" &&
                    (messages.length === 0 ||
                      (messages.at(-1)?.role === "assistant" &&
                        (messages.at(-1) as { items: AssistantItem[] }).items.length === 0)) && (
                      <TypingBubble />
                    )}
                  <div ref={bottomRef} />
                </div>
              </div>

              <div className="shrink-0 border-t border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3">
                <div className="max-w-3xl mx-auto">
                  <ChatInputBar
                    input={input}
                    setInput={setInput}
                    textareaRef={textareaRef}
                    pendingFile={pendingFile}
                    setPendingFile={setPendingFile}
                    fileInputRef={fileInputRef}
                    onSend={sendMessage}
                    disabled={phase === "uploading" || phase === "running"}
                    placeholder={
                      phase === "running"   ? "Analysing…"  :
                      phase === "uploading" ? "Uploading…"  :
                      "Ask a follow-up question…"
                    }
                  />
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Welcome / empty state
// ─────────────────────────────────────────────────────────────────────────────

interface WelcomeStateProps {
  fileInputRef: RefObject<HTMLInputElement>;
  pendingFile: File | null;
  setPendingFile: (f: File | null) => void;
  processFile: (file: File) => void;
  input: string;
  setInput: (v: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  onSend: () => void;
}

const WELCOME_EXAMPLES = [
  "Which products are driving the most revenue?",
  "Find patterns and anomalies in this dataset",
  "What factors correlate with the outcome variable?",
  "Run a linear regression and explain the results",
];

function WelcomeState({
  fileInputRef, pendingFile, setPendingFile, processFile,
  input, setInput, textareaRef, onSend,
}: WelcomeStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 pb-8">
      <div className="w-full max-w-2xl flex flex-col items-center gap-8">

        <div className="text-center space-y-3">
          <h2 className="text-3xl font-bold tracking-tight text-[var(--text-primary)]">
            What would you like to analyse?
          </h2>
          <p className="text-[var(--text-secondary)] text-base leading-relaxed">
            Drop a CSV or Excel file and ask anything — correlations, regressions, trends, charts, anomalies.
          </p>
        </div>

        {/* Upload zone + input */}
        <div className="w-full rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-surface)] p-1 transition-all hover:border-brand-400">
          <div
            className="flex items-center gap-3 px-4 pt-4 pb-2 cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
              <UploadIcon />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {pendingFile ? pendingFile.name : "Attach a file or drag & drop anywhere"}
              </p>
              <p className="text-xs text-[var(--text-muted)]">CSV, XLSX, XLS — up to 50 MB</p>
            </div>
            {pendingFile && (
              <button
                className="ml-auto text-[var(--text-muted)] hover:text-red-500 transition-colors"
                onClick={(e) => { e.stopPropagation(); setPendingFile(null); }}
              >
                ✕
              </button>
            )}
          </div>

          <div className="mx-4 border-t border-[var(--border-subtle)]" />

          <ChatInputBar
            input={input}
            setInput={setInput}
            textareaRef={textareaRef}
            pendingFile={pendingFile}
            setPendingFile={setPendingFile}
            fileInputRef={fileInputRef}
            onSend={onSend}
            disabled={false}
            placeholder="Attach a file and describe what you need, or drop a file to get started…"
            borderless
            onFileSelect={processFile}
          />
        </div>

        {/* Example prompts */}
        <div className="w-full space-y-2">
          <p className="text-xs text-[var(--text-muted)] font-medium uppercase tracking-wider text-center">
            Try asking
          </p>
          <div className="grid grid-cols-2 gap-2">
            {WELCOME_EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setInput(ex)}
                className="text-left text-sm px-4 py-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--text-secondary)] hover:border-brand-400 hover:text-[var(--text-primary)] transition-all"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) setPendingFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar section
// ─────────────────────────────────────────────────────────────────────────────

function SidebarSection({
  label, icon, open, onToggle, count, extra, children,
}: {
  label: string;
  icon: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  count?: number;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-[var(--border)]">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-[var(--bg-elevated)] transition-colors group"
      >
        <span className="text-[var(--text-muted)] group-hover:text-[var(--text-secondary)] transition-colors">
          {icon}
        </span>
        <span className="flex-1 text-left text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider group-hover:text-[var(--text-secondary)] transition-colors">
          {label}
        </span>
        {count !== undefined && count > 0 && (
          <span className="text-xs text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1.5 py-0.5 rounded-full border border-[var(--border)]">
            {count}
          </span>
        )}
        {extra && <span onClick={(e) => e.stopPropagation()}>{extra}</span>}
        <svg
          className={`w-3.5 h-3.5 text-[var(--text-muted)] transition-transform duration-150 ${open ? "rotate-0" : "-rotate-90"}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="px-2 pb-2 flex flex-col gap-0.5 max-h-60 overflow-y-auto">
          {children}
        </div>
      )}
    </div>
  );
}

// Collapsed sidebar icon button
function SidebarIconBtn({
  title, icon, badge, onClick,
}: {
  title: string;
  icon: React.ReactNode;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="relative w-9 h-9 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
    >
      {icon}
      {badge !== undefined && badge > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-3.5 rounded-full bg-brand-500 text-white text-[9px] font-bold flex items-center justify-center px-0.5">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat input bar
// ─────────────────────────────────────────────────────────────────────────────

interface ChatInputBarProps {
  input: string;
  setInput: (v: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  pendingFile: File | null;
  setPendingFile: (f: File | null) => void;
  fileInputRef: RefObject<HTMLInputElement>;
  onSend: () => void;
  disabled: boolean;
  placeholder: string;
  borderless?: boolean;
  onFileSelect?: (file: File) => void;
}

function ChatInputBar({
  input, setInput, textareaRef, pendingFile, setPendingFile,
  fileInputRef, onSend, disabled, placeholder, borderless, onFileSelect,
}: ChatInputBarProps) {
  const autoResize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  };

  const handleKey = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!disabled) onSend(); }
  };

  const canSend = (input.trim().length > 0 || pendingFile !== null) && !disabled;

  return (
    <div className={`flex items-end gap-2 ${borderless ? "px-3 py-2" : ""}`}>
      {!borderless && (
        <>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-brand-500 hover:bg-brand-500/10 transition-colors mb-0.5"
            title="Attach file"
          >
            <PaperclipIcon />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) { if (onFileSelect) onFileSelect(file); else setPendingFile(file); }
              e.target.value = "";
            }}
          />
        </>
      )}

      {pendingFile && !borderless && (
        <div className="shrink-0 flex items-center gap-1.5 bg-brand-500/10 border border-brand-500/30 text-brand-600 dark:text-brand-400 text-xs px-2.5 py-1.5 rounded-lg mb-0.5">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span className="max-w-[120px] truncate">{pendingFile.name}</span>
          <button onClick={() => setPendingFile(null)} className="ml-1 hover:text-red-500">✕</button>
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={input}
        rows={1}
        disabled={disabled}
        onChange={(e) => { setInput(e.target.value); autoResize(); }}
        onKeyDown={handleKey}
        placeholder={placeholder}
        className="flex-1 resize-none bg-transparent text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none leading-relaxed py-1.5 max-h-40 disabled:opacity-50"
      />

      <button
        onClick={onSend}
        disabled={!canSend}
        className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center bg-brand-500 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-brand-600 transition-colors mb-0.5"
      >
        <SendIcon />
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Message row
// ─────────────────────────────────────────────────────────────────────────────

function MessageRow({ msg }: { msg: ChatMsg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end animate-fade-up">
        <div className="max-w-[75%] bg-brand-500 text-white px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed">
          {msg.text}
        </div>
      </div>
    );
  }

  if (msg.role === "file") {
    return (
      <div className="flex justify-end animate-fade-up">
        <div className="flex items-center gap-2.5 bg-[var(--bg-elevated)] border border-[var(--border)] px-4 py-3 rounded-2xl rounded-br-sm text-sm">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
            msg.status === "loading" ? "bg-amber-400/10" : msg.status === "error" ? "bg-red-400/10" : "bg-brand-500/10"
          }`}>
            {msg.status === "loading" ? (
              <SpinnerIcon className="text-amber-500" />
            ) : msg.status === "error" ? (
              <span className="text-red-500 text-xs">✕</span>
            ) : (
              <svg className="w-4 h-4 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            )}
          </div>
          <div>
            <p className="font-medium text-[var(--text-primary)] text-xs truncate max-w-[200px]">{msg.filename}</p>
            <p className="text-xs text-[var(--text-muted)]">
              {msg.status === "loading" ? "Uploading & analysing…" :
               msg.status === "error"   ? msg.error :
               `${msg.rows.toLocaleString()} rows · ${msg.cols} columns`}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start animate-fade-up">
      <div className="shrink-0 w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center mr-3 mt-0.5">
        <span className="text-white text-xs font-bold">DW</span>
      </div>
      <div className="flex-1 min-w-0 space-y-3">
        {msg.items.length === 0 && msg.streaming ? (
          <TypingBubble />
        ) : (
          msg.items.map((item, i) => <AssistantItemView key={i} item={item} />)
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Assistant item renderers
// ─────────────────────────────────────────────────────────────────────────────

function AssistantItemView({ item }: { item: AssistantItem }) {
  switch (item.kind) {
    case "tool":
      return <ToolRow label={item.label} result={item.result} />;
    case "finding":
      return <FindingCard headline={item.headline} detail={item.detail} stat={item.stat} />;
    case "chart":
      return <ChartCard figure={item.figure} title={item.title} />;
    case "report":
      return (
        <div className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-2xl p-5 text-sm text-[var(--text-primary)] leading-relaxed">
          <SimpleMarkdown text={item.markdown} />
        </div>
      );
    case "error":
      return (
        <div className="bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 rounded-xl px-4 py-3 text-sm">
          {item.message}
        </div>
      );
  }
}

function ToolRow({ label, result }: { label: string; result?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
      <div className="w-1.5 h-1.5 rounded-full bg-brand-500/60 shrink-0" />
      <span>{label}</span>
      {result ? (
        <>
          <span className="text-[var(--border)]">·</span>
          <span className="text-[var(--text-muted)] truncate max-w-[240px]">{result}</span>
        </>
      ) : (
        <span className="dot-1 inline-block w-1 h-1 rounded-full bg-brand-500/60" />
      )}
    </div>
  );
}

function FindingCard({ headline, detail, stat }: { headline: string; detail: string; stat?: string }) {
  return (
    <div className="bg-[var(--bg-surface)] border border-brand-500/20 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="w-6 h-6 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="font-semibold text-sm text-[var(--text-primary)]">{headline}</p>
          {stat && <p className="text-xl font-bold text-brand-500 mt-0.5">{stat}</p>}
          <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">{detail}</p>
        </div>
      </div>
    </div>
  );
}

function ChartCard({ figure, title }: { figure: PlotlyFigure; title: string }) {
  const isEmpty = !figure.data || (figure.data as unknown[]).length === 0;

  return (
    <div className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-2xl overflow-hidden">
      {title && (
        <div className="px-4 pt-3 pb-1 flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-brand-500 shrink-0" />
          <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{title}</p>
        </div>
      )}
      {isEmpty ? (
        <div className="flex flex-col items-center justify-center gap-2 h-32 text-[var(--text-muted)] text-xs px-4">
          <svg className="w-6 h-6 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
          <span className="text-center">Chart not stored (session reloaded) — ask the assistant to regenerate it.</span>
        </div>
      ) : (
        <Plot
          data={figure.data as Plotly.Data[]}
          layout={{
            ...(figure.layout as Partial<Plotly.Layout>),
            autosize: true,
            margin: { t: title ? 12 : 28, r: 24, b: 48, l: 56 },
            font: { family: "Inter, sans-serif", size: 11 },
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            legend: { orientation: "h", y: -0.18, font: { size: 10 } },
          }}
          config={{ displayModeBar: true, displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "toImage"] }}
          style={{ width: "100%", height: 360 }}
          useResizeHandler
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Markdown renderer — handles headings, lists, code blocks, bold/italic
// ─────────────────────────────────────────────────────────────────────────────

function SimpleMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      nodes.push(
        <pre key={i} className="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-4 my-3 overflow-x-auto">
          <code className={`text-xs font-mono text-[var(--text-secondary)] ${lang ? `language-${lang}` : ""}`}>
            {codeLines.join("\n")}
          </code>
        </pre>
      );
      i++;
      continue;
    }

    // HR
    if (/^[-*_]{3,}$/.test(line.trim())) {
      nodes.push(<hr key={i} className="border-[var(--border)] my-4" />);
      i++; continue;
    }

    // Headings
    if (line.startsWith("### ")) {
      nodes.push(<h3 key={i} className="font-semibold text-sm text-[var(--text-primary)] mt-5 mb-1.5">{line.slice(4)}</h3>);
      i++; continue;
    }
    if (line.startsWith("## ")) {
      nodes.push(<h2 key={i} className="font-bold text-base text-brand-500 mt-6 mb-2 pb-1 border-b border-brand-500/20">{line.slice(3)}</h2>);
      i++; continue;
    }
    if (line.startsWith("# ")) {
      nodes.push(<h1 key={i} className="font-bold text-lg text-[var(--text-primary)] mt-6 mb-2">{line.slice(2)}</h1>);
      i++; continue;
    }

    // Bullet list — collect consecutive bullets
    if (line.startsWith("- ") || line.startsWith("* ")) {
      const items: string[] = [];
      while (i < lines.length && (lines[i].startsWith("- ") || lines[i].startsWith("* "))) {
        items.push(lines[i].slice(2));
        i++;
      }
      nodes.push(
        <ul key={i} className="list-disc ml-5 space-y-1 my-2">
          {items.map((it, j) => (
            <li key={j} className="text-sm text-[var(--text-secondary)] leading-relaxed">
              <InlineMd text={it} />
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // Numbered list — collect consecutive numbered items
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      nodes.push(
        <ol key={i} className="list-decimal ml-5 space-y-1 my-2">
          {items.map((it, j) => (
            <li key={j} className="text-sm text-[var(--text-secondary)] leading-relaxed">
              <InlineMd text={it} />
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      nodes.push(
        <blockquote key={i} className="border-l-2 border-brand-500/40 pl-3 my-2 text-sm text-[var(--text-secondary)] italic">
          <InlineMd text={line.slice(2)} />
        </blockquote>
      );
      i++; continue;
    }

    // Blank line
    if (line.trim() === "") {
      nodes.push(<div key={i} className="h-1.5" />);
      i++; continue;
    }

    // Regular paragraph
    nodes.push(
      <p key={i} className="text-sm text-[var(--text-primary)] leading-relaxed">
        <InlineMd text={line} />
      </p>
    );
    i++;
  }

  return <>{nodes}</>;
}

function InlineMd({ text }: { text: string }) {
  // Split on bold (**text**), italic (*text*), and inline code (`code`)
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={i} className="font-semibold text-[var(--text-primary)]">{part.slice(2, -2)}</strong>;
        if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
          return <em key={i} className="italic text-[var(--text-secondary)]">{part.slice(1, -1)}</em>;
        if (part.startsWith("`") && part.endsWith("`"))
          return <code key={i} className="font-mono text-xs bg-[var(--bg-elevated)] border border-[var(--border)] px-1 py-0.5 rounded text-brand-500">{part.slice(1, -1)}</code>;
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sheet picker modal
// ─────────────────────────────────────────────────────────────────────────────

function SheetPicker({ sheets, onPick, onDismiss }: { sheets: string[]; onPick: (s: string) => void; onDismiss: () => void }) {
  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-[var(--bg-surface)] border border-[var(--border)] rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <h3 className="font-semibold text-[var(--text-primary)] mb-1">Multiple sheets found</h3>
        <p className="text-sm text-[var(--text-secondary)] mb-4">Which sheet would you like to analyse?</p>
        <div className="flex flex-col gap-2">
          {sheets.map((s) => (
            <button key={s} onClick={() => onPick(s)} className="w-full text-left px-4 py-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border)] text-sm text-[var(--text-primary)] hover:border-brand-400 hover:bg-brand-500/5 transition-all">
              {s}
            </button>
          ))}
        </div>
        <button onClick={onDismiss} className="mt-3 w-full text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Misc small components
// ─────────────────────────────────────────────────────────────────────────────

function TypingBubble() {
  return (
    <div className="flex items-center gap-1 px-1 py-1">
      <span className="dot-1 inline-block w-2 h-2 rounded-full bg-[var(--text-muted)]" />
      <span className="dot-2 inline-block w-2 h-2 rounded-full bg-[var(--text-muted)]" />
      <span className="dot-3 inline-block w-2 h-2 rounded-full bg-[var(--text-muted)]" />
    </div>
  );
}

function ThemeToggle({ theme, toggle }: { theme: string; toggle: () => void }) {
  return (
    <button
      onClick={toggle}
      className="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Date helper
// ─────────────────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  const d   = new Date(iso);
  const now = new Date();
  const diffMs   = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1)  return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24)  return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7)  return `${diffDays} days ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

function SidebarToggleIcon({ open }: { open: boolean }) {
  return open ? (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
    </svg>
  ) : (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
    </svg>
  );
}

function ReportsIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function ChatsIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  );
}

function ViewIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  );
}

function PaperclipIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg className="w-4 h-4 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
    </svg>
  );
}

function SpinnerIcon({ className }: { className?: string }) {
  return (
    <svg className={`w-4 h-4 animate-spin ${className}`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
    </svg>
  );
}
