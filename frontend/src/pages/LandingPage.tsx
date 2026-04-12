/**
 * LandingPage — informational and tutorial entry point.
 * Introduces the product, explains capabilities, walks through usage,
 * shows example prompts, and provides a single CTA to launch the app.
 */

import { useNavigate } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";

// ─────────────────────────────────────────────────────────────────────────────
// Data
// ─────────────────────────────────────────────────────────────────────────────

const CAPABILITIES = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
    title: "Data Cleaning",
    desc: "Fixes missing values, removes duplicates, corrects inconsistent formatting, and standardises types — automatically.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
    title: "Exploratory Analysis",
    desc: "Examines distributions, correlations, summary statistics, and unusual patterns to give you a thorough overview.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: "Data Visualisation",
    desc: "Generates charts, heatmaps, scatter plots, bar charts, and interactive dashboards — choosing the best format automatically.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
      </svg>
    ),
    title: "Statistical Analysis",
    desc: "Runs hypothesis tests, regression, correlation, ANOVA, and confidence intervals with clear plain-English explanations.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
    title: "Predictive Analysis",
    desc: "Builds forecasting models from historical data to predict future outcomes — sales, churn, trends — with accuracy metrics.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M10 21h7a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v11m0 5l4.879-4.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242z" />
      </svg>
    ),
    title: "Diagnostic Analysis",
    desc: "Investigates unexpected drops, spikes, or anomalies — isolating root causes and quantifying each contributing factor.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    title: "Prescriptive Analysis",
    desc: "Recommends concrete actions ranked by likely impact, so you can make informed decisions immediately.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    title: "Reporting",
    desc: "Compiles findings into structured reports — executive summary, key takeaways, charts, and detailed breakdowns.",
  },
];

const STEPS = [
  {
    num: "01",
    title: "Upload your data",
    desc: "Drop a CSV or Excel file into the chat. The AI reads it, identifies the structure, and cleans it automatically.",
  },
  {
    num: "02",
    title: "Describe what you need",
    desc: "Type your question or goal in plain English. No code, no formulas, no technical knowledge required.",
  },
  {
    num: "03",
    title: "Get your answer",
    desc: "The AI analyses your data, generates charts and findings, and explains everything in a clear, structured report.",
  },
];

const EXAMPLES = [
  "Which products are driving the most revenue?",
  "Find anomalies and outliers in this dataset",
  "What factors correlate with customer churn?",
  "Run a linear regression and explain the results",
  "Show me the distribution of all numeric columns",
  "What caused the drop in sales last quarter?",
  "Which customer segments should we focus on?",
  "Predict next month's values based on historical trends",
];

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]">

      {/* ── Navigation ─────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-30 bg-[var(--bg-base)]/80 backdrop-blur-md border-b border-[var(--border)]">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight">
            Data<span className="text-brand-500">Weaver</span>
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              className="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <button
              onClick={() => navigate("/chat")}
              className="btn-primary text-sm px-4 py-2"
            >
              Launch App
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden py-24 px-6">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-brand-500/8 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-4xl mx-auto text-center space-y-8">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 text-brand-600 dark:text-brand-400 text-xs font-medium px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
            AI-powered data analysis
          </div>

          {/* Headline */}
          <h1 className="text-5xl sm:text-6xl font-bold tracking-tight leading-tight text-[var(--text-primary)]">
            Your personal<br />
            <span className="text-brand-500">AI data analyst</span>
          </h1>

          {/* Sub-headline */}
          <p className="text-xl text-[var(--text-secondary)] max-w-2xl mx-auto leading-relaxed">
            Upload any dataset and describe what you need in plain language.
            DataWeaver cleans, analyses, and visualises your data — giving you
            answers in seconds, not hours.
          </p>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => navigate("/chat")}
              className="btn-primary text-base px-8 py-3.5 shadow-lg shadow-brand-500/20 hover:shadow-brand-500/30 transition-shadow"
            >
              Start Analysing — it&apos;s free
            </button>
            <p className="text-sm text-[var(--text-muted)]">
              No account required · CSV &amp; Excel supported
            </p>
          </div>
        </div>
      </section>

      {/* ── Capabilities ─────────────────────────────────────────────────── */}
      <section className="py-20 px-6 bg-[var(--bg-surface)]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14 space-y-3">
            <h2 className="text-3xl font-bold tracking-tight">Everything you need from an analyst</h2>
            <p className="text-[var(--text-secondary)] max-w-xl mx-auto">
              DataWeaver handles the full analysis pipeline — from raw data to
              actionable insights — entirely through conversation.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {CAPABILITIES.map((cap) => (
              <div
                key={cap.title}
                className="group p-5 rounded-2xl bg-[var(--bg-base)] border border-[var(--border)] hover:border-brand-400/50 hover:shadow-sm transition-all"
              >
                <div className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-500 mb-4 group-hover:bg-brand-500/15 transition-colors">
                  {cap.icon}
                </div>
                <h3 className="font-semibold text-sm text-[var(--text-primary)] mb-1.5">{cap.title}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{cap.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14 space-y-3">
            <h2 className="text-3xl font-bold tracking-tight">How it works</h2>
            <p className="text-[var(--text-secondary)]">
              Three steps from raw data to clear answers.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((step, i) => (
              <div key={step.num} className="relative flex flex-col items-center text-center">
                {/* Connector line */}
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-[calc(50%+32px)] right-[-calc(50%-32px)] h-px bg-[var(--border)] w-[calc(100%-64px)]" style={{ width: "calc(100% - 64px)", left: "calc(50% + 32px)" }} />
                )}

                {/* Step number */}
                <div className="w-16 h-16 rounded-2xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center mb-5 shrink-0">
                  <span className="text-xl font-bold text-brand-500">{step.num}</span>
                </div>

                <h3 className="font-semibold text-base text-[var(--text-primary)] mb-2">{step.title}</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Example prompts ───────────────────────────────────────────────── */}
      <section className="py-20 px-6 bg-[var(--bg-surface)]">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12 space-y-3">
            <h2 className="text-3xl font-bold tracking-tight">What can you ask?</h2>
            <p className="text-[var(--text-secondary)]">
              Anything you would ask a human analyst — just type it out.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {EXAMPLES.map((ex) => (
              <div
                key={ex}
                className="flex items-center gap-3 px-5 py-4 rounded-xl bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-secondary)]"
              >
                <svg className="w-4 h-4 text-brand-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span>&ldquo;{ex}&rdquo;</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ─────────────────────────────────────────────────────── */}
      <section className="py-24 px-6">
        <div className="max-w-2xl mx-auto text-center space-y-6">
          <h2 className="text-4xl font-bold tracking-tight">
            Ready to analyse your data?
          </h2>
          <p className="text-[var(--text-secondary)] text-lg leading-relaxed">
            No setup, no code, no expertise needed. Just upload your file and
            start asking questions.
          </p>
          <button
            onClick={() => navigate("/chat")}
            className="btn-primary text-base px-10 py-4 shadow-lg shadow-brand-500/20 hover:shadow-brand-500/30 transition-shadow"
          >
            Start Analysing Now
          </button>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-[var(--border)] py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            Data<span className="text-brand-500">Weaver</span>
          </span>
          <p className="text-xs text-[var(--text-muted)]">
            AI-powered data analysis · Upload · Ask · Understand
          </p>
        </div>
      </footer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

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
