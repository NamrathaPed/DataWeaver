import { useState } from "react";
import type { FilterOptions } from "@/services/api";

interface Props {
  options: FilterOptions;
  onApply: (filters: {
    numeric_filters?: Record<string, { min?: number; max?: number }>;
    category_filters?: Record<string, string[]>;
    date_filters?: Record<string, { start?: string; end?: string }>;
  }) => void;
  isLoading: boolean;
  summary: { filtered: number; original: number } | null;
}

export default function FilterPanel({ options, onApply, isLoading, summary }: Props) {
  const [numericFilters, setNumericFilters] = useState<Record<string, { min?: number; max?: number }>>({});
  const [categoryFilters, setCategoryFilters] = useState<Record<string, string[]>>({});
  const [dateFilters, setDateFilters] = useState<Record<string, { start?: string; end?: string }>>({});

  const hasFilters =
    Object.keys(numericFilters).length > 0 ||
    Object.keys(categoryFilters).length > 0 ||
    Object.keys(dateFilters).length > 0;

  const handleReset = () => {
    setNumericFilters({});
    setCategoryFilters({});
    setDateFilters({});
    onApply({});
  };

  return (
    <div className="card sticky top-20 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-800">Filters</h2>
        {hasFilters && (
          <button onClick={handleReset} className="text-xs text-gray-400 hover:text-red-500 transition-colors">
            Reset all
          </button>
        )}
      </div>

      {/* Filter summary */}
      {summary && (
        <div className="bg-brand-50 rounded-xl px-3 py-2 text-sm">
          <span className="font-semibold text-brand-600">{summary.filtered.toLocaleString()}</span>
          <span className="text-gray-500"> / {summary.original.toLocaleString()} rows</span>
        </div>
      )}

      {/* Numeric range filters */}
      {Object.entries(options.numeric).map(([col, range]) => (
        <div key={col}>
          <label className="block text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">
            {col}
          </label>
          <div className="flex gap-2">
            <input
              type="number"
              placeholder={`Min (${range.min})`}
              step={range.step}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              onChange={(e) => {
                const val = e.target.value === "" ? undefined : Number(e.target.value);
                setNumericFilters((prev) => ({
                  ...prev,
                  [col]: { ...prev[col], min: val },
                }));
              }}
            />
            <input
              type="number"
              placeholder={`Max (${range.max})`}
              step={range.step}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              onChange={(e) => {
                const val = e.target.value === "" ? undefined : Number(e.target.value);
                setNumericFilters((prev) => ({
                  ...prev,
                  [col]: { ...prev[col], max: val },
                }));
              }}
            />
          </div>
        </div>
      ))}

      {/* Categorical filters */}
      {Object.entries(options.categorical).map(([col, values]) => (
        <div key={col}>
          <label className="block text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">
            {col}
          </label>
          <div className="max-h-36 overflow-y-auto space-y-1">
            {values.map((val) => {
              const selected = categoryFilters[col]?.includes(val) ?? false;
              return (
                <label key={val} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={selected}
                    className="rounded border-gray-300 text-brand-500 focus:ring-brand-500"
                    onChange={() => {
                      setCategoryFilters((prev) => {
                        const current = prev[col] ?? [];
                        const next = selected
                          ? current.filter((v) => v !== val)
                          : [...current, val];
                        if (next.length === 0) {
                          const { [col]: _, ...rest } = prev;
                          return rest;
                        }
                        return { ...prev, [col]: next };
                      });
                    }}
                  />
                  <span className="text-sm text-gray-600 group-hover:text-gray-900 truncate">{val}</span>
                </label>
              );
            })}
          </div>
        </div>
      ))}

      {/* Date filters */}
      {Object.entries(options.datetime).map(([col, bounds]) => (
        <div key={col}>
          <label className="block text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">
            {col}
          </label>
          <div className="space-y-1.5">
            <input
              type="date"
              defaultValue={bounds.start?.slice(0, 10)}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              onChange={(e) =>
                setDateFilters((prev) => ({
                  ...prev,
                  [col]: { ...prev[col], start: e.target.value || undefined },
                }))
              }
            />
            <input
              type="date"
              defaultValue={bounds.end?.slice(0, 10)}
              className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              onChange={(e) =>
                setDateFilters((prev) => ({
                  ...prev,
                  [col]: { ...prev[col], end: e.target.value || undefined },
                }))
              }
            />
          </div>
        </div>
      ))}

      {/* Apply button */}
      <button
        className="btn-primary w-full"
        disabled={isLoading}
        onClick={() =>
          onApply({
            numeric_filters: Object.keys(numericFilters).length ? numericFilters : undefined,
            category_filters: Object.keys(categoryFilters).length ? categoryFilters : undefined,
            date_filters: Object.keys(dateFilters).length ? dateFilters : undefined,
          })
        }
      >
        {isLoading ? "Applying..." : "Apply Filters"}
      </button>
    </div>
  );
}
