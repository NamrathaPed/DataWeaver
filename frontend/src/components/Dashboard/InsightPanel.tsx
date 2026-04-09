import { useMutation, useQueryClient } from "@tanstack/react-query";
import { regenerateSection, type InsightResult } from "@/services/api";

interface Props {
  sessionId: string;
  data?: InsightResult;
  isLoading: boolean;
  error?: string;
}

export default function InsightPanel({ sessionId, data, isLoading, error }: Props) {
  if (isLoading) return <Skeleton />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Meta */}
      {data._meta && (
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span className="badge bg-gray-100 text-gray-500">{data._meta.model}</span>
          <span>{data._meta.total_tokens.toLocaleString()} tokens used</span>
          {data._meta.failed_sections.length > 0 && (
            <span className="text-amber-500">
              {data._meta.failed_sections.length} section(s) failed
            </span>
          )}
        </div>
      )}

      {/* Overview */}
      {data.overview?.length > 0 && (
        <InsightSection title="Dataset Overview" sectionKey="overview" sessionId={sessionId}>
          <ul className="space-y-3">
            {data.overview.map((item, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-brand-500 shrink-0" />
                <div>
                  <p className="text-gray-700">{item.point}</p>
                  <p className="text-xs text-gray-400 mt-0.5">Stat: {item.stat_referenced}</p>
                </div>
              </li>
            ))}
          </ul>
        </InsightSection>
      )}

      {/* Correlations */}
      {data.correlations?.length > 0 && (
        <InsightSection title="Correlations" sectionKey="correlations" sessionId={sessionId}>
          <div className="space-y-3">
            {data.correlations.map((item, i) => (
              <div key={i} className="flex gap-3 p-3 bg-gray-50 rounded-xl">
                <CorrelationBadge r={item.r} />
                <div>
                  <p className="text-sm font-medium text-gray-700">
                    {item.col_a} &rarr; {item.col_b}
                  </p>
                  <p className="text-sm text-gray-500 mt-0.5">{item.insight}</p>
                </div>
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* Distributions */}
      {data.distributions?.length > 0 && (
        <InsightSection title="Distributions" sectionKey="distributions" sessionId={sessionId}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.distributions.map((item, i) => (
              <div key={i} className="p-3 bg-gray-50 rounded-xl">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-gray-800 text-sm">{item.column}</span>
                  <span className="badge bg-blue-50 text-blue-600 text-xs">{item.skew_label}</span>
                </div>
                <p className="text-sm text-gray-500">{item.insight}</p>
                {item.outlier_pct > 0 && (
                  <p className="text-xs text-amber-500 mt-1">{item.outlier_pct}% outliers</p>
                )}
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* Categorical */}
      {data.categorical?.length > 0 && (
        <InsightSection title="Categories" sectionKey="categorical" sessionId={sessionId}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.categorical.map((item, i) => (
              <div key={i} className="p-3 bg-gray-50 rounded-xl">
                <span className="font-medium text-gray-800 text-sm">{item.column}</span>
                <p className="text-sm text-gray-500 mt-1">{item.insight}</p>
                {item.dominant_value && (
                  <p className="text-xs text-gray-400 mt-1">
                    Top: <span className="font-medium">{item.dominant_value}</span>
                    {item.dominant_pct ? ` (${item.dominant_pct}%)` : ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* Time series */}
      {data.time_series?.length > 0 && (
        <InsightSection title="Time Series" sectionKey="time_series" sessionId={sessionId}>
          <div className="space-y-3">
            {data.time_series.map((item, i) => (
              <div key={i} className="p-3 bg-gray-50 rounded-xl flex gap-3">
                <span className="badge bg-green-50 text-green-600 self-start">{item.frequency}</span>
                <div>
                  <p className="text-sm font-medium text-gray-700">{item.column}</p>
                  <p className="text-sm text-gray-500 mt-0.5">{item.insight}</p>
                  {item.has_gaps && <p className="text-xs text-amber-500 mt-1">Gaps detected in time series</p>}
                </div>
              </div>
            ))}
          </div>
        </InsightSection>
      )}

      {/* Anomalies */}
      {data.anomalies?.length > 0 && (
        <InsightSection title="Data Quality Issues" sectionKey="anomalies" sessionId={sessionId}>
          <div className="space-y-3">
            {data.anomalies.map((item, i) => (
              <div key={i} className="p-3 bg-amber-50 border border-amber-100 rounded-xl">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-amber-800 text-sm">{item.column}</span>
                  <span className="badge bg-amber-100 text-amber-700 text-xs">{item.issue}</span>
                </div>
                <p className="text-sm text-amber-700">{item.recommendation}</p>
              </div>
            ))}
          </div>
        </InsightSection>
      )}
    </div>
  );
}

function InsightSection({
  title,
  sectionKey,
  sessionId,
  children,
}: {
  title: string;
  sectionKey: string;
  sessionId: string;
  children: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => regenerateSection(sessionId, sectionKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["insights", sessionId] });
    },
  });

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-800">{title}</h2>
        <button
          className="btn-secondary text-xs py-1.5 px-3"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Regenerating..." : "Regenerate"}
        </button>
      </div>
      {children}
    </div>
  );
}

function CorrelationBadge({ r }: { r: number }) {
  const abs = Math.abs(r);
  const color =
    abs >= 0.8 ? "bg-red-100 text-red-700" :
    abs >= 0.6 ? "bg-orange-100 text-orange-700" :
    "bg-blue-100 text-blue-700";

  return (
    <span className={`badge ${color} self-start shrink-0 font-mono`}>
      r={r > 0 ? "+" : ""}{r.toFixed(2)}
    </span>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {[...Array(4)].map((_, i) => <div key={i} className="h-40 bg-gray-100 rounded-2xl" />)}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card border-red-100 bg-red-50 text-red-700">
      <p className="font-medium">Error generating insights</p>
      <p className="text-sm mt-1">{message}</p>
    </div>
  );
}
