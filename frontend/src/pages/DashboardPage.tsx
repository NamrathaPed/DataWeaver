import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  fetchCharts,
  generateInsights,
  fetchFilterOptions,
  applyFilters,
  type ChartsResponse,
} from "@/services/api";
import DataPreview from "@/components/Dashboard/DataPreview";
import SummaryStats from "@/components/Dashboard/SummaryStats";
import ChartGrid from "@/components/Dashboard/ChartGrid";
import InsightPanel from "@/components/Dashboard/InsightPanel";
import FilterPanel from "@/components/Dashboard/FilterPanel";

type Tab = "preview" | "stats" | "charts" | "insights";

export default function DashboardPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("preview");
  const [filteredPreview, setFilteredPreview] = useState<Record<string, unknown>[] | null>(null);
  const [filteredCharts, setFilteredCharts] = useState<unknown | null>(null);
  const [filterSummary, setFilterSummary] = useState<{ filtered: number; original: number } | null>(null);

  if (!sessionId) {
    navigate("/");
    return null;
  }

  const chartsQuery = useQuery({
    queryKey: ["charts", sessionId],
    queryFn: () => fetchCharts(sessionId),
    enabled: activeTab === "charts",
  });

  const insightsQuery = useQuery({
    queryKey: ["insights", sessionId],
    queryFn: () => generateInsights(sessionId),
    enabled: activeTab === "insights",
  });

  const filterOptsQuery = useQuery({
    queryKey: ["filter-options", sessionId],
    queryFn: () => fetchFilterOptions(sessionId),
  });

  const filterMutation = useMutation({
    mutationFn: (filters: Parameters<typeof applyFilters>[1]) =>
      applyFilters(sessionId, filters),
    onSuccess: (data) => {
      setFilteredPreview(data.preview);
      setFilteredCharts(data.charts ?? null);
      setFilterSummary({ filtered: data.filtered_rows, original: data.original_rows });
      if (activeTab === "charts" && data.charts) setActiveTab("charts");
    },
  });

  const tabs: { id: Tab; label: string }[] = [
    { id: "preview", label: "Data Preview" },
    { id: "stats", label: "Summary Stats" },
    { id: "charts", label: "Charts" },
    { id: "insights", label: "AI Insights" },
  ];

  const charts = (filteredCharts as ChartsResponse["charts"] | null) ?? chartsQuery.data?.charts;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center justify-between">
          <button
            onClick={() => navigate("/")}
            className="text-xl font-bold text-gray-900 tracking-tight"
          >
            Data<span className="text-brand-500">Weaver</span>
          </button>
          <nav className="flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
                  ${activeTab === t.id
                    ? "bg-brand-50 text-brand-600"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                  }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className="max-w-screen-xl mx-auto px-6 py-8 flex gap-6">
        {/* Sidebar — filters */}
        {filterOptsQuery.data && (
          <aside className="w-72 shrink-0">
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
            <DataPreview
              sessionId={sessionId}
              overrideData={filteredPreview}
            />
          )}
          {activeTab === "stats" && (
            <SummaryStats sessionId={sessionId} />
          )}
          {activeTab === "charts" && (
            <ChartGrid
              charts={charts}
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
      </div>
    </div>
  );
}
