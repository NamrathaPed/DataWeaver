/**
 * API service layer — all calls to the FastAPI backend.
 * Uses axios with a shared base URL so we only change it in one place.
 */

import axios from "axios";

const http = axios.create({ baseURL: "/api" });

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadResponse {
  session_id: string;
  upload_id: string | null;
  filename: string;
  extension: string;
  row_count: number;
  col_count: number;
  size_kb: number | null;
  columns: string[];
  preview: Record<string, unknown>[];
  cached: boolean;
  requires_sheet_selection?: boolean;
  sheets?: string[];
}

export interface AnalyzeResponse {
  session_id: string;
  cleaning_report: CleaningReport;
  eda: EDAResult;
}

export interface CleaningReport {
  original_shape: { rows: number; cols: number };
  final_shape: { rows: number; cols: number };
  duplicates_removed: number;
  columns_filled: Record<string, { strategy: string; fill_value: unknown; rows_filled: number }>;
  columns_type_cast: Record<string, string>;
  columns_dropped: string[];
  warnings: string[];
}

export interface EDAResult {
  column_types: {
    numeric: string[];
    categorical: string[];
    datetime: string[];
    boolean: string[];
    high_cardinality: string[];
  };
  summary: Record<string, ColumnSummary>;
  correlations: {
    matrix: Record<string, Record<string, number | null>>;
    strong_pairs: CorrelationPair[];
    threshold: number;
  };
  distributions: Record<string, DistributionInfo>;
  categorical: Record<string, CategoricalInfo>;
  time_series: Record<string, TimeSeriesInfo>;
  dataset_overview: DatasetOverview;
}

export interface ColumnSummary {
  type: string;
  count: number;
  null_count: number;
  null_pct: number;
  mean?: number;
  median?: number;
  std?: number;
  min?: number;
  max?: number;
  unique?: number;
  top_values?: Record<string, number>;
  mode?: string;
}

export interface CorrelationPair {
  col_a: string;
  col_b: string;
  r: number;
  strength: string;
  direction: string;
}

export interface DistributionInfo {
  skewness: number;
  skew_label: string;
  kurtosis: number;
  outlier_count: number;
  outlier_pct: number;
  iqr: number;
  is_normal: boolean | null;
  normality_p: number | null;
  histogram: { counts: number[]; bin_edges: number[] };
}

export interface CategoricalInfo {
  unique_count: number;
  value_counts: Record<string, number>;
  entropy: number;
  distribution: string;
}

export interface TimeSeriesInfo {
  min: string;
  max: string;
  range_days: number;
  record_count: number;
  inferred_frequency: string;
  is_monotonic: boolean;
  has_gaps: boolean;
}

export interface DatasetOverview {
  rows: number;
  cols: number;
  total_cells: number;
  total_nulls: number;
  null_pct: number;
  memory_kb: number;
  columns: string[];
  dtypes: Record<string, string>;
  null_per_column: Record<string, number>;
}

export interface ChartsResponse {
  session_id: string;
  charts: {
    histograms: PlotlyFigure[];
    bar_charts: PlotlyFigure[];
    line_charts: PlotlyFigure[];
    scatter_plots: PlotlyFigure[];
    box_plots: PlotlyFigure[];
    correlation_heatmap: PlotlyFigure | null;
  };
  cached: boolean;
}

export interface PlotlyFigure {
  data: unknown[];
  layout: Record<string, unknown>;
}

export interface InsightsResponse {
  session_id: string;
  insights: InsightResult;
  cached: boolean;
}

export interface InsightResult {
  overview: { point: string; stat_referenced: string }[];
  statistics: { column: string; insight: string; stat_referenced: string }[];
  correlations: { col_a: string; col_b: string; r: number; insight: string; direction: string }[];
  distributions: { column: string; insight: string; skew_label: string; outlier_pct: number }[];
  categorical: { column: string; insight: string; dominant_value: string | null; dominant_pct: number | null }[];
  time_series: { column: string; insight: string; frequency: string; has_gaps: boolean }[];
  anomalies: { column: string; issue: string; recommendation: string }[];
  _meta: { model: string; total_tokens: number; failed_sections: unknown[] };
}

export interface FilterOptions {
  numeric: Record<string, { min: number; max: number; step: number }>;
  categorical: Record<string, string[]>;
  datetime: Record<string, { start: string; end: string }>;
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

export async function uploadFile(
  file: File,
  sessionId?: string
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (sessionId) form.append("session_id", sessionId);
  const { data } = await http.post<UploadResponse>("/upload", form);
  return data;
}

export async function selectSheet(
  file: File,
  sheetName: string,
  sessionId?: string
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("sheet_name", sheetName);
  if (sessionId) form.append("session_id", sessionId);
  const { data } = await http.post<UploadResponse>("/upload/sheet", form);
  return data;
}

// ---------------------------------------------------------------------------
// Analyze
// ---------------------------------------------------------------------------

export async function analyzeDataset(
  sessionId: string,
  options?: {
    numeric_fill_strategy?: string;
    drop_high_null_cols?: boolean;
    null_col_threshold?: number;
  }
): Promise<AnalyzeResponse> {
  const params = new URLSearchParams({ session_id: sessionId });
  if (options?.numeric_fill_strategy)
    params.append("numeric_fill_strategy", options.numeric_fill_strategy);
  if (options?.drop_high_null_cols !== undefined)
    params.append("drop_high_null_cols", String(options.drop_high_null_cols));
  if (options?.null_col_threshold !== undefined)
    params.append("null_col_threshold", String(options.null_col_threshold));
  const { data } = await http.post<AnalyzeResponse>(`/analyze?${params}`);
  return data;
}

// ---------------------------------------------------------------------------
// Charts
// ---------------------------------------------------------------------------

export async function fetchCharts(
  sessionId: string,
  forceRefresh = false
): Promise<ChartsResponse> {
  const { data } = await http.get<ChartsResponse>("/charts/all", {
    params: { session_id: sessionId, force_refresh: forceRefresh },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------

export async function generateInsights(
  sessionId: string,
  forceRefresh = false
): Promise<InsightsResponse> {
  const { data } = await http.post<InsightsResponse>("/insights/generate", null, {
    params: { session_id: sessionId, force_refresh: forceRefresh },
  });
  return data;
}

export async function regenerateSection(
  sessionId: string,
  section: string
): Promise<{ section: string; insights: unknown[] }> {
  const { data } = await http.post("/insights/section", null, {
    params: { session_id: sessionId, section },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export async function fetchFilterOptions(sessionId: string): Promise<FilterOptions> {
  const { data } = await http.get<{ options: FilterOptions }>("/filters/options", {
    params: { session_id: sessionId },
  });
  return data.options;
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatResponse {
  reply: string;
  chart: PlotlyFigure | null;
  chart_config: Record<string, string> | null;
  data_table: Record<string, unknown>[] | null;
  suggested_questions: string[];
}

export async function sendChatMessage(
  sessionId: string,
  message: string
): Promise<ChatResponse> {
  const { data } = await http.post<ChatResponse>("/chat/message", {
    session_id: sessionId,
    message,
  });
  return data;
}

export async function getChatHistory(
  sessionId: string
): Promise<{ history: { role: string; content: string }[] }> {
  const { data } = await http.get(`/chat/history?session_id=${sessionId}`);
  return data;
}

export async function clearChatHistory(sessionId: string): Promise<void> {
  await http.post(`/chat/clear?session_id=${sessionId}`);
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------

export type AgentEvent =
  | { type: "thinking"; text: string }
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; summary: string }
  | { type: "chart"; figure: PlotlyFigure; title: string }
  | { type: "finding"; headline: string; detail: string; stat?: string }
  | { type: "report"; markdown: string }
  | { type: "done" }
  | { type: "error"; message: string };

/**
 * Stream an agentic analysis via SSE.
 * Calls onEvent for each parsed event, returns a cleanup function.
 */
export function runAgentAnalysis(
  sessionId: string,
  problem: string,
  onEvent: (event: AgentEvent) => void,
  onError?: (err: Error) => void
): () => void {
  let active = true;

  (async () => {
    try {
      const response = await fetch("/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, problem }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Agent request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (active) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const raw = line.slice(6).trim();
            if (!raw) continue;
            try {
              const event = JSON.parse(raw) as AgentEvent;
              if (active) onEvent(event);
            } catch {
              // malformed event — skip
            }
          }
        }
      }
    } catch (err) {
      if (active && onError) onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return () => { active = false; };
}

export async function applyFilters(
  sessionId: string,
  filters: {
    numeric_filters?: Record<string, { min?: number; max?: number }>;
    category_filters?: Record<string, string[]>;
    date_filters?: Record<string, { start?: string; end?: string }>;
  }
): Promise<{
  filtered_rows: number;
  original_rows: number;
  reduction_pct: number;
  preview: Record<string, unknown>[];
  charts?: ChartsResponse["charts"];
}> {
  const { data } = await http.post("/filters/apply", {
    session_id: sessionId,
    ...filters,
    regenerate_charts: true,
  });
  return data;
}
