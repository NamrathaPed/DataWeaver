import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Plot from "react-plotly.js";
import {
  sendChatMessage,
  getChatHistory,
  clearChatHistory,
  type ChatResponse,
  type PlotlyFigure,
} from "@/services/api";

interface Props {
  sessionId: string;
  onAddChartToDashboard?: (chart: PlotlyFigure, title: string) => void;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  chart?: PlotlyFigure | null;
  chart_config?: Record<string, string> | null;
  suggested_questions?: string[];
}

export default function ChatPanel({ sessionId, onAddChartToDashboard }: Props) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  // Load existing history on mount
  useQuery({
    queryKey: ["chat-history", sessionId],
    queryFn: () => getChatHistory(sessionId),
    onSuccess: (data: { history: { role: string; content: string }[] }) => {
      if (data.history.length > 0 && messages.length === 0) {
        setMessages(
          data.history.map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content,
          }))
        );
      }
    },
  } as Parameters<typeof useQuery>[0]);

  const mutation = useMutation({
    mutationFn: (message: string) => sendChatMessage(sessionId, message),
    onSuccess: (data: ChatResponse) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          chart: data.chart,
          chart_config: data.chart_config,
          suggested_questions: data.suggested_questions,
        },
      ]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I couldn't process that. Please try again.",
        },
      ]);
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => clearChatHistory(sessionId),
    onSuccess: () => {
      setMessages([]);
      queryClient.invalidateQueries({ queryKey: ["chat-history", sessionId] });
    },
  });

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = (text?: string) => {
    const msg = text ?? input.trim();
    if (!msg || mutation.isPending) return;

    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    mutation.mutate(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const suggestedQuestions =
    messages.length === 0
      ? [
          "What are the key insights in this dataset?",
          "Which columns have missing values?",
          "Show me the strongest correlations",
          "What anomalies exist in the data?",
        ]
      : (lastAssistant?.suggested_questions ?? []);

  return (
    <div className="flex flex-col h-full bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-green-400" />
          <h2 className="font-semibold text-gray-800">Data Analyst</h2>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => clearMutation.mutate()}
            className="text-xs text-gray-400 hover:text-red-400 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-0">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-8">
            <p className="text-2xl mb-2">🤖</p>
            <p className="font-medium text-gray-600">Ask me anything about your data</p>
            <p className="text-sm mt-1">I can answer questions, find patterns, and generate charts</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            message={msg}
            onAddToDashboard={
              msg.chart && onAddChartToDashboard
                ? () => onAddChartToDashboard(
                    msg.chart!,
                    msg.chart_config?.title ?? "Chart"
                  )
                : undefined
            }
          />
        ))}

        {mutation.isPending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {suggestedQuestions.length > 0 && !mutation.isPending && (
        <div className="px-5 py-3 border-t border-gray-50">
          <div className="flex flex-wrap gap-2">
            {suggestedQuestions.map((q: string, i: number) => (
              <button
                key={i}
                onClick={() => handleSend(q)}
                className="text-xs bg-brand-50 text-brand-600 hover:bg-brand-100
                           rounded-lg px-3 py-1.5 transition-colors text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="px-5 py-4 border-t border-gray-100">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question or request a chart..."
            rows={1}
            className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-2.5
                       text-sm focus:outline-none focus:ring-2 focus:ring-brand-500
                       placeholder-gray-400 max-h-32 overflow-y-auto"
            style={{ minHeight: "42px" }}
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || mutation.isPending}
            className="btn-primary px-4 py-2.5 shrink-0"
          >
            <SendIcon />
          </button>
        </div>
        <p className="text-xs text-gray-300 mt-1.5 pl-1">Press Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  onAddToDashboard,
}: {
  message: Message;
  onAddToDashboard?: () => void;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] space-y-3 ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        {/* Bubble */}
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
            ${isUser
              ? "bg-brand-500 text-white rounded-br-sm"
              : "bg-gray-50 text-gray-800 rounded-bl-sm border border-gray-100"
            }`}
        >
          {message.content}
        </div>

        {/* Chart */}
        {message.chart && (
          <div className="w-full bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
            <Plot
              data={message.chart.data as Plotly.Data[]}
              layout={{
                ...(message.chart.layout as Partial<Plotly.Layout>),
                autosize: true,
                height: 320,
                margin: { t: 40, b: 40, l: 50, r: 20 },
                paper_bgcolor: "rgba(0,0,0,0)",
                plot_bgcolor: "rgba(0,0,0,0)",
                font: { family: "Inter, ui-sans-serif", size: 12 },
              }}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: "100%" }}
              useResizeHandler
            />
            {onAddToDashboard && (
              <div className="px-4 py-2 border-t border-gray-50 flex justify-end">
                <button
                  onClick={onAddToDashboard}
                  className="text-xs text-brand-600 hover:text-brand-700 font-medium
                             flex items-center gap-1 transition-colors"
                >
                  <span>+</span> Add to dashboard
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.269 20.876L5.999 12zm0 0h7.5" />
    </svg>
  );
}
