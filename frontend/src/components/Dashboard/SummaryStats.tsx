import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import type { EDAResult, ColumnSummary } from "@/services/api";

interface Props {
  sessionId: string;
}

export default function SummaryStats({ sessionId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["summary", sessionId],
    queryFn: async () => {
      const res = await axios.get(`/api/analyze/summary?session_id=${sessionId}`);
      return res.data as { summary: EDAResult["summary"]; dataset_overview: EDAResult["dataset_overview"] };
    },
  });

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorBox message={(error as Error).message} />;

  const summary = data?.summary ?? {};
  const numeric = Object.entries(summary).filter(([, v]) => v.type === "numeric");
  const categorical = Object.entries(summary).filter(([, v]) => v.type === "categorical");
  const datetime = Object.entries(summary).filter(([, v]) => v.type === "datetime");

  return (
    <div className="space-y-8">
      {/* Numeric */}
      {numeric.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Numeric Columns</h2>
          <div className="overflow-x-auto card p-0">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {["Column", "Count", "Nulls %", "Mean", "Median", "Std Dev", "Min", "Max"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {numeric.map(([col, info]) => (
                  <NumericRow key={col} col={col} info={info} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Categorical */}
      {categorical.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Categorical Columns</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {categorical.map(([col, info]) => (
              <CategoricalCard key={col} col={col} info={info} />
            ))}
          </div>
        </section>
      )}

      {/* Datetime */}
      {datetime.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Datetime Columns</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {datetime.map(([col, info]) => (
              <DateCard key={col} col={col} info={info} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function NumericRow({ col, info }: { col: string; info: ColumnSummary }) {
  const fmt = (v: number | undefined) =>
    v === undefined ? "—" : Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v.toFixed(4);

  return (
    <tr className="hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">{col}</td>
      <td className="px-4 py-3 text-gray-600">{info.count.toLocaleString()}</td>
      <td className={`px-4 py-3 ${(info.null_pct ?? 0) > 10 ? "text-amber-600 font-medium" : "text-gray-600"}`}>
        {info.null_pct?.toFixed(1)}%
      </td>
      <td className="px-4 py-3 text-gray-600 font-mono">{fmt(info.mean)}</td>
      <td className="px-4 py-3 text-gray-600 font-mono">{fmt(info.median)}</td>
      <td className="px-4 py-3 text-gray-600 font-mono">{fmt(info.std)}</td>
      <td className="px-4 py-3 text-gray-600 font-mono">{fmt(info.min)}</td>
      <td className="px-4 py-3 text-gray-600 font-mono">{fmt(info.max)}</td>
    </tr>
  );
}

function CategoricalCard({ col, info }: { col: string; info: ColumnSummary }) {
  const topValues = Object.entries(info.top_values ?? {}).slice(0, 5);
  const total = info.count;

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-gray-800">{col}</h3>
        <span className="badge bg-purple-50 text-purple-600">{info.unique} unique</span>
      </div>
      <div className="space-y-2">
        {topValues.map(([val, cnt]) => {
          const pct = ((cnt / total) * 100).toFixed(1);
          return (
            <div key={val}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600 truncate max-w-[70%]">{val}</span>
                <span className="text-gray-400">{pct}%</span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 rounded-full"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      {info.null_pct > 0 && (
        <p className="mt-3 text-xs text-amber-500">{info.null_pct.toFixed(1)}% missing</p>
      )}
    </div>
  );
}

function DateCard({ col, info }: { col: string; info: ColumnSummary }) {
  return (
    <div className="card">
      <h3 className="font-semibold text-gray-800 mb-3">{col}</h3>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-gray-400">Earliest</dt>
        <dd className="text-gray-700 font-mono">{String(info.min).slice(0, 10)}</dd>
        <dt className="text-gray-400">Latest</dt>
        <dd className="text-gray-700 font-mono">{String(info.max).slice(0, 10)}</dd>
        <dt className="text-gray-400">Records</dt>
        <dd className="text-gray-700">{info.count.toLocaleString()}</dd>
        <dt className="text-gray-400">Unique</dt>
        <dd className="text-gray-700">{info.unique?.toLocaleString()}</dd>
      </dl>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 bg-gray-100 rounded w-48" />
      <div className="h-64 bg-gray-100 rounded-2xl" />
      <div className="h-8 bg-gray-100 rounded w-48" />
      <div className="grid grid-cols-2 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-40 bg-gray-100 rounded-2xl" />)}
      </div>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card border-red-100 bg-red-50 text-red-700">
      <p className="font-medium">Error loading statistics</p>
      <p className="text-sm mt-1">{message}</p>
    </div>
  );
}
