import Plot from "react-plotly.js";
import type { ChartsResponse, PlotlyFigure } from "@/services/api";

interface Props {
  charts?: ChartsResponse["charts"];
  isLoading: boolean;
  error?: string;
}

export default function ChartGrid({ charts, isLoading, error }: Props) {
  if (isLoading) return <Skeleton />;
  if (error) return <ErrorBox message={error} />;
  if (!charts) return <EmptyState />;

  const sections: { title: string; figures: PlotlyFigure[] }[] = [
    { title: "Distributions", figures: charts.histograms },
    { title: "Categories", figures: charts.bar_charts },
    { title: "Time Series", figures: charts.line_charts },
    { title: "Correlations", figures: charts.scatter_plots },
    { title: "Comparisons", figures: charts.box_plots },
  ].filter((s) => s.figures?.length > 0);

  return (
    <div className="space-y-10">
      {/* Correlation heatmap — full width */}
      {charts.correlation_heatmap && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Correlation Heatmap</h2>
          <div className="card p-2">
            <PlotChart figure={charts.correlation_heatmap} />
          </div>
        </section>
      )}

      {sections.map((section) => (
        <section key={section.title}>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">{section.title}</h2>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {section.figures.map((fig, i) => (
              <div key={i} className="card p-2">
                <PlotChart figure={fig} />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function PlotChart({ figure }: { figure: PlotlyFigure }) {
  return (
    <Plot
      data={figure.data as Plotly.Data[]}
      layout={{
        ...(figure.layout as Partial<Plotly.Layout>),
        autosize: true,
        margin: { t: 50, b: 40, l: 60, r: 20 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, ui-sans-serif" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "400px" }}
      useResizeHandler
    />
  );
}

function Skeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 animate-pulse">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="h-[400px] bg-gray-100 rounded-2xl" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card text-center py-20 text-gray-400">
      <p className="font-medium">No charts available yet.</p>
      <p className="text-sm mt-1">Charts generate automatically after analysis completes.</p>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card border-red-100 bg-red-50 text-red-700">
      <p className="font-medium">Error generating charts</p>
      <p className="text-sm mt-1">{message}</p>
    </div>
  );
}
