import { useQuery } from "@tanstack/react-query";
import axios from "axios";

interface Props {
  sessionId: string;
  overrideData?: Record<string, unknown>[] | null;
}

const TYPE_STYLES: Record<string, { label: string; color: string }> = {
  numeric:          { label: "Numeric",       color: "bg-blue-50 text-blue-700" },
  currency:         { label: "Currency",      color: "bg-emerald-50 text-emerald-700" },
  percentage:       { label: "Percentage",    color: "bg-teal-50 text-teal-700" },
  categorical:      { label: "Categorical",   color: "bg-purple-50 text-purple-700" },
  ordinal:          { label: "Ordinal",       color: "bg-violet-50 text-violet-700" },
  boolean:          { label: "Boolean",       color: "bg-orange-50 text-orange-700" },
  datetime:         { label: "Datetime",      color: "bg-green-50 text-green-700" },
  geospatial:       { label: "Geospatial",    color: "bg-sky-50 text-sky-700" },
  id:               { label: "Identifier",    color: "bg-red-50 text-red-400" },
  high_cardinality: { label: "Free Text",     color: "bg-gray-100 text-gray-500" },
};

export default function DataPreview({ sessionId, overrideData }: Props) {
  const summaryQuery = useQuery({
    queryKey: ["preview", sessionId],
    queryFn: async () => {
      const res = await axios.get(`/api/analyze/summary?session_id=${sessionId}`);
      return res.data as {
        summary: Record<string, unknown>;
        dataset_overview: {
          rows: number; cols: number; null_pct: number;
          memory_kb: number; columns: string[];
        };
      };
    },
  });

  const colTypesQuery = useQuery({
    queryKey: ["column-types", sessionId],
    queryFn: async () => {
      const res = await axios.get(`/api/analyze/column-types?session_id=${sessionId}`);
      return res.data.column_types as Record<string, string[]>;
    },
  });

  if (summaryQuery.isLoading) return <Skeleton />;
  if (summaryQuery.error) return <ErrorBox message={(summaryQuery.error as Error).message} />;

  const overview = summaryQuery.data?.dataset_overview;
  const colTypes = colTypesQuery.data;

  // Build a map of column → semantic type
  const colTypeMap: Record<string, string> = {};
  if (colTypes) {
    for (const [type, cols] of Object.entries(colTypes)) {
      for (const col of cols) colTypeMap[col] = type;
    }
  }

  return (
    <div className="space-y-6">
      {/* Overview stat cards */}
      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard label="Rows" value={overview.rows.toLocaleString()} />
          <StatCard label="Columns" value={overview.cols.toString()} />
          <StatCard label="Missing %" value={`${overview.null_pct}%`} warn={overview.null_pct > 10} />
          <StatCard label="Memory" value={`${Math.round(overview.memory_kb)} KB`} />
        </div>
      )}

      {/* Column type groups */}
      {colTypes && (
        <div className="card space-y-4">
          <h3 className="font-semibold text-gray-800">Column Classification</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(TYPE_STYLES).map(([type, style]) => {
              const cols = colTypes[type] ?? [];
              if (cols.length === 0) return null;
              return (
                <div key={type} className="rounded-xl border border-gray-100 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className={`badge ${style.color} font-medium`}>{style.label}</span>
                    <span className="text-xs text-gray-400">{cols.length} column{cols.length !== 1 ? "s" : ""}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {cols.map((col) => (
                      <span key={col} className="text-xs bg-gray-50 border border-gray-100 rounded-lg px-2 py-1 text-gray-700 font-mono">
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Data table */}
      {overrideData && overrideData.length > 0 ? (
        <DataTable rows={overrideData} colTypeMap={colTypeMap} />
      ) : (
        <div className="card text-center text-gray-400 py-16">
          <p className="font-medium text-gray-500">Apply filters to preview filtered rows here.</p>
          <p className="text-sm mt-1">The full dataset summary is shown above.</p>
        </div>
      )}
    </div>
  );
}

function DataTable({
  rows,
  colTypeMap,
}: {
  rows: Record<string, unknown>[];
  colTypeMap: Record<string, string>;
}) {
  const columns = Object.keys(rows[0]);

  return (
    <div className="card overflow-hidden p-0">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">Filtered Preview</h3>
        <span className="text-sm text-gray-400">{rows.length} rows shown</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              {columns.map((col) => {
                const type = colTypeMap[col];
                const style = type ? TYPE_STYLES[type] : null;
                return (
                  <th key={col} className="px-4 py-3 text-left whitespace-nowrap">
                    <div className="flex flex-col gap-1">
                      <span className="font-medium text-gray-700">{col}</span>
                      {style && (
                        <span className={`badge ${style.color} text-xs w-fit`}>{style.label}</span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {rows.slice(0, 100).map((row, i) => (
              <tr key={i} className="hover:bg-gray-50 transition-colors">
                {columns.map((col) => {
                  const val = row[col];
                  return (
                    <td key={col} className="px-4 py-2.5 font-mono text-xs whitespace-nowrap max-w-xs truncate text-gray-700">
                      {val === null || val === undefined ? (
                        <span className="text-gray-300 italic">null</span>
                      ) : String(val)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="card">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${warn ? "text-amber-500" : "text-gray-900"}`}>{value}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-gray-100 rounded-2xl" />)}
      </div>
      <div className="h-64 bg-gray-100 rounded-2xl" />
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card border-red-100 bg-red-50 text-red-700">
      <p className="font-medium">Error loading preview</p>
      <p className="text-sm mt-1">{message}</p>
    </div>
  );
}
