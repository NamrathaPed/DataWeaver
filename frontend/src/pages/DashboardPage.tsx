import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  analyzeDataset,
  fetchCharts,
  generateInsights,
  fetchFilterOptions,
  applyFilters,
  type ChartsResponse,
  type PlotlyFigure,
} from "@/services/api";
import DataPreview from "@/components/Dashboard/DataPreview";
import SummaryStats from "@/components/Dashboard/SummaryStats";
import ChartGrid from "@/components/Dashboard/ChartGrid";
import InsightPanel from "@/components/Dashboard/InsightPanel";
import FilterPanel from "@/components/Dashboard/FilterPanel";
import ChatPanel from "@/components/Dashboard/ChatPanel";

type Tab = "preview" | "stats" | "charts" | "insights";

export default function DashboardPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("preview");
  const [filteredPreview, setFilteredPreview] = useState<Record<string, unknown>[] | null>(null);
  const [filteredCharts, setFilteredCharts] = useState<unknown | null>(null);
  const [filterSummary, setFilterSummary] = useState<{ filtered: number; original: number } | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [extraCharts, setExtraCharts] = useState<{ chart: PlotlyFigure; title: string }[]>([]);

  const { theme, toggle: toggleTheme } = useTheme();
  if (!sessionId) { navigate("/"); return null; }

  const analyzeQuery = useQuery({
    queryKey: ["analyze", sessionId],
    queryFn: () => analyzeDataset(sessionId),
    retry: false,
  });

  const isReady = analyzeQuery.isSuccess;

  const chartsQuery = useQuery({
    queryKey: ["charts", sessionId],
    queryFn: () => fetchCharts(sessionId),
    enabled: isReady && activeTab === "charts",
  });

  const insightsQuery = useQuery({
    queryKey: ["insights", sessionId],
    queryFn: () => generateInsights(sessionId),
    enabled: isReady && activeTab === "insights",
  });

  const filterOptsQuery = useQuery({
    queryKey: ["filter-options", sessionId],
    queryFn: () => fetchFilterOptions(sessionId),
    enabled: isReady,
  });

  const filterMutation = useMutation({
    mutationFn: (filters: Parameters<typeof applyFilters>[1]) =>
      applyFilters(sessionId, filters),
    onSuccess: (data) => {
      setFilteredPreview(data.preview);
      setFilteredCharts(data.charts ?? null);
      setFilterSummary({ filtered: data.filtered_rows, original: data.original_rows });
    },
  });

  const tabs: { id: Tab; label: string }[] = [
    { id: "preview", label: "Data Preview" },
    { id: "stats", label: "Summary Stats" },
    { id: "charts", label: "Charts" },
    { id: "insights", label: "AI Insights" },
  ];

  const charts = (filteredCharts as ChartsResponse["charts"] | null) ?? chartsQuery.data?.charts;

  // Merge chat-generated charts into the charts view
  const chartsWithExtras = charts
    ? {
        ...charts,
        histograms: [
          ...charts.histograms,
          ...extraCharts.filter((_, i) => i % 2 === 0).map((c) => c.chart),
        ],
      }
    : undefined;

  if (analyzeQuery.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center space-y-3">
          <Spinner />
          <p className="text-gray-600 font-medium">Loading dataset…</p>
          <p className="text-gray-400 text-sm">Cleaning data and computing statistics</p>
        </div>
      </div>
    );
  }

  if (analyzeQuery.isError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center space-y-4">
          <p className="text-gray-800 font-semibold text-lg">Session not found</p>
          <p className="text-gray-500 text-sm max-w-xs">
            This session may have expired. Please upload your file again.
          </p>
          <button
            onClick={() => navigate("/")}
            className="btn-primary text-sm"
          >
            ← Back to DataWeaver
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-screen-2xl mx-auto px-6 h-14 flex items-center justify-between">
          <button onClick={() => navigate("/")} className="text-xl font-bold text-gray-900 tracking-tight">
            Data<span className="text-brand-500">Weaver</span>
          </button>
          <nav className="flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
                  ${activeTab === t.id ? "bg-brand-50 text-brand-600" : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"}`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setChatOpen((v) => !v)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors
                ${chatOpen ? "bg-brand-500 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              <ChatIcon />
              {chatOpen ? "Hide Chat" : "Ask AI"}
            </button>
            <button
              onClick={toggleTheme}
              className="w-9 h-9 rounded-xl flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-500 dark:hover:text-gray-200 dark:hover:bg-gray-800 transition-colors"
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 max-w-screen-2xl mx-auto w-full px-6 py-8 flex gap-6">

        {/* Left sidebar — filters */}
        {filterOptsQuery.data && (
          <aside className="w-64 shrink-0">
            <FilterPanel
              options={filterOptsQuery.data}
              onApply={(filters) => filterMutation.mutate(filters)}
              isLoading={filterMutation.isPending}
              summary={filterSummary}
            />
          </aside>
        )}

        {/* Main content */}
        <main className="flex-1 min-w-0">
          {activeTab === "preview" && (
            <DataPreview sessionId={sessionId} overrideData={filteredPreview} />
          )}
          {activeTab === "stats" && <SummaryStats sessionId={sessionId} />}
          {activeTab === "charts" && (
            <ChartGrid
              charts={chartsWithExtras}
              isLoading={chartsQuery.isLoading}
              error={chartsQuery.error?.message}
            />
          )}
          {activeTab === "insights" && (
            <InsightPanel
              sessionId={sessionId}
              data={insightsQuery.data?.insights}
              isLoading={insightsQuery.isLoading}
              error={insightsQuery.error?.message}
            />
          )}
        </main>

        {/* Right sidebar — chat */}
        {chatOpen && (
          <aside className="w-96 shrink-0">
            <div className="sticky top-20 h-[calc(100vh-6rem)]">
              <ChatPanel
                sessionId={sessionId}
                onAddChartToDashboard={(chart, title) => {
                  setExtraCharts((prev) => [...prev, { chart, title }]);
                  setActiveTab("charts");
                }}
              />
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-8 w-8 text-brand-500 mx-auto" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

function ChatIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
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
