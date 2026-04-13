/**
 * LandingPage — animated entry point for DataWeaver.
 * Uses Framer Motion for entrance animations, scroll-triggered reveals,
 * floating background elements, and smooth interactions.
 */

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  motion,
  useScroll,
  useTransform,
  AnimatePresence,
} from "framer-motion";
import { useTheme } from "@/hooks/useTheme";

// ─────────────────────────────────────────────────────────────────────────────
// Animation variants
// Keep transitions out of variant definitions to avoid Easing type conflicts.
// Transition config goes on each motion element directly.
// ─────────────────────────────────────────────────────────────────────────────

const fadeUp = {
  hidden:  { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0 },
};

const staggerContainer = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const staggerFast = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.05 } },
};

// ─────────────────────────────────────────────────────────────────────────────
// Data
// ─────────────────────────────────────────────────────────────────────────────

const CAPABILITIES = [
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />,
    title: "Data Cleaning",
    desc: "Fixes missing values, removes duplicates, corrects formatting, and standardises types — automatically.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />,
    title: "Exploratory Analysis",
    desc: "Examines distributions, correlations, and unusual patterns to give you a thorough overview.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />,
    title: "Data Visualisation",
    desc: "Generates charts, heatmaps, scatter plots, and dashboards — choosing the best format for your data.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />,
    title: "Statistical Analysis",
    desc: "Runs hypothesis tests, regression, ANOVA, and confidence intervals with clear plain-English explanations.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />,
    title: "Predictive Analysis",
    desc: "Builds forecasting models to predict future outcomes — sales, churn, trends — with accuracy metrics.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M10 21h7a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v11m0 5l4.879-4.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242z" />,
    title: "Diagnostic Analysis",
    desc: "Investigates unexpected drops, spikes, or anomalies — isolating root causes and quantifying each factor.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />,
    title: "Prescriptive Analysis",
    desc: "Recommends concrete actions ranked by likely impact, so you can make informed decisions immediately.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />,
    title: "Reporting",
    desc: "Compiles findings into structured reports — executive summary, key takeaways, and detailed breakdowns.",
  },
];

const STEPS = [
  {
    num: "01",
    title: "Upload your data",
    desc: "Drop a CSV or Excel file. The AI reads it, identifies the structure, and cleans it automatically.",
  },
  {
    num: "02",
    title: "Describe what you need",
    desc: "Type your question in plain English. No code, no formulas, no technical knowledge required.",
  },
  {
    num: "03",
    title: "Get your answer",
    desc: "The AI analyses, generates charts and findings, and explains everything in a clear report.",
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
// Cycling prompt component
// ─────────────────────────────────────────────────────────────────────────────

function CyclingPrompt() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setIndex((i) => (i + 1) % EXAMPLES.length), 2800);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="h-8 overflow-hidden flex items-center justify-center">
      <AnimatePresence mode="wait">
        <motion.span
          key={index}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -14 }}
          transition={{ duration: 0.35, ease: "circOut" }}
          className="text-brand-500 font-medium text-base sm:text-lg"
        >
          &ldquo;{EXAMPLES[index]}&rdquo;
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scroll-reveal wrapper
// ─────────────────────────────────────────────────────────────────────────────

function Reveal({
  children,
  variants = fadeUp,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  variants?: typeof fadeUp;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={variants}
      transition={{ duration: 0.55, ease: "easeOut", delay }}
    >
      {children}
    </motion.div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const { scrollY } = useScroll();
  const navBg = useTransform(scrollY, [0, 60], ["rgba(0,0,0,0)", "rgba(0,0,0,0.04)"]);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] overflow-x-hidden">

      {/* ── Navigation ───────────────────────────────────────────────────── */}
      <motion.nav
        style={{ backgroundColor: navBg }}
        className="fixed top-0 left-0 right-0 z-30 backdrop-blur-md border-b border-[var(--border)]"
      >
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <motion.span
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-xl font-bold tracking-tight"
          >
            Data<span className="text-brand-500">Weaver</span>
          </motion.span>

          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="flex items-center gap-3"
          >
            <button
              onClick={toggle}
              className="w-9 h-9 rounded-xl flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors"
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              className="btn-primary text-sm px-4 py-2"
            >
              Launch App
            </motion.button>
          </motion.div>
        </div>
      </motion.nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-6 pt-16">

        {/* Animated background orbs */}
        <div className="absolute inset-0 pointer-events-none">
          <motion.div
            animate={{ x: [0, 40, 0], y: [0, -30, 0], scale: [1, 1.1, 1] }}
            transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
            className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-brand-500/10 rounded-full blur-3xl"
          />
          <motion.div
            animate={{ x: [0, -30, 0], y: [0, 40, 0], scale: [1, 1.15, 1] }}
            transition={{ duration: 15, repeat: Infinity, ease: "easeInOut", delay: 2 }}
            className="absolute bottom-1/4 right-1/3 w-[400px] h-[400px] bg-indigo-500/8 rounded-full blur-3xl"
          />
          <motion.div
            animate={{ x: [0, 20, 0], y: [0, -20, 0] }}
            transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            className="absolute top-1/2 right-1/4 w-[300px] h-[300px] bg-brand-400/6 rounded-full blur-3xl"
          />
        </div>

        <div className="relative max-w-4xl mx-auto text-center">

          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2, ease: "circOut" }}
            className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 text-brand-600 dark:text-brand-400 text-xs font-medium px-3 py-1.5 rounded-full mb-8"
          >
            <motion.span
              animate={{ scale: [1, 1.4, 1], opacity: [1, 0.5, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
              className="w-1.5 h-1.5 rounded-full bg-brand-500 inline-block"
            />
            AI-powered data analysis
          </motion.div>

          {/* Headline — words animate in individually */}
          <motion.h1
            variants={staggerFast}
            initial="hidden"
            animate="visible"
            className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] mb-6"
          >
            {["Your", "personal"].map((word) => (
              <motion.span key={word} variants={fadeUp} className="inline-block mr-[0.25em]">
                {word}
              </motion.span>
            ))}
            <br />
            {["AI", "data", "analyst"].map((word, i) => (
              <motion.span
                key={word}
                variants={fadeUp}
                className={`inline-block mr-[0.25em] ${i >= 0 ? "text-brand-500" : ""}`}
              >
                {word}
              </motion.span>
            ))}
          </motion.h1>

          {/* Sub-headline */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65, ease: "circOut" }}
            className="text-xl text-[var(--text-secondary)] max-w-2xl mx-auto leading-relaxed mb-10"
          >
            Upload any dataset and describe what you need in plain language.
            DataWeaver cleans, analyses, and visualises your data — giving you
            answers in seconds, not hours.
          </motion.p>

          {/* CTA */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.8, ease: "circOut" }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16"
          >
            <motion.button
              whileHover={{ scale: 1.05, boxShadow: "0 20px 40px rgba(29,150,148,0.25)" }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              className="btn-primary text-base px-9 py-4 shadow-lg shadow-brand-500/20 relative overflow-hidden"
            >
              {/* Shimmer effect */}
              <motion.span
                animate={{ x: ["-100%", "200%"] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 1.5 }}
                className="absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/20 to-transparent skew-x-12"
              />
              Start Analysing — it&apos;s free
            </motion.button>
            <p className="text-sm text-[var(--text-muted)]">
              No account required · CSV &amp; Excel supported
            </p>
          </motion.div>

          {/* Cycling prompt */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.1, duration: 0.6 }}
            className="space-y-2"
          >
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-widest">
              People are asking
            </p>
            <CyclingPrompt />
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.6, duration: 0.6 }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1"
        >
          <motion.div
            animate={{ y: [0, 8, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            className="w-5 h-8 rounded-full border-2 border-[var(--border)] flex items-start justify-center pt-1.5"
          >
            <div className="w-1 h-2 rounded-full bg-[var(--text-muted)]" />
          </motion.div>
          <p className="text-[10px] text-[var(--text-muted)] tracking-widest uppercase">Scroll</p>
        </motion.div>
      </section>

      {/* ── Capabilities ─────────────────────────────────────────────────── */}
      <section className="py-24 px-6 bg-[var(--bg-surface)]">
        <div className="max-w-6xl mx-auto">

          <Reveal className="text-center mb-16 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
              Everything you need from an analyst
            </h2>
            <p className="text-[var(--text-secondary)] max-w-xl mx-auto">
              DataWeaver handles the full analysis pipeline — from raw data to
              actionable insights — entirely through conversation.
            </p>
          </Reveal>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5"
          >
            {CAPABILITIES.map((cap) => (
              <motion.div
                key={cap.title}
                variants={fadeUp}
                whileHover={{ y: -4, boxShadow: "0 12px 30px rgba(0,0,0,0.08)" }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className="group p-5 rounded-2xl bg-[var(--bg-base)] border border-[var(--border)] hover:border-brand-400/50 cursor-default"
              >
                <motion.div
                  whileHover={{ scale: 1.12, rotate: 5 }}
                  transition={{ type: "spring", stiffness: 400, damping: 15 }}
                  className="w-10 h-10 rounded-xl bg-brand-500/10 flex items-center justify-center text-brand-500 mb-4 group-hover:bg-brand-500/20 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    {cap.icon}
                  </svg>
                </motion.div>
                <h3 className="font-semibold text-sm text-[var(--text-primary)] mb-1.5">{cap.title}</h3>
                <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{cap.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="py-24 px-6">
        <div className="max-w-4xl mx-auto">

          <Reveal className="text-center mb-16 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">How it works</h2>
            <p className="text-[var(--text-secondary)]">Three steps from raw data to clear answers.</p>
          </Reveal>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 md:grid-cols-3 gap-8"
          >
            {STEPS.map((step, i) => (
              <motion.div
                key={step.num}
                variants={fadeUp}
                className="relative flex flex-col items-center text-center"
              >
                {/* Animated connector line */}
                {i < STEPS.length - 1 && (
                  <motion.div
                    initial={{ scaleX: 0 }}
                    whileInView={{ scaleX: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.4 + i * 0.2, ease: "circOut" }}
                    style={{ originX: 0 }}
                    className="hidden md:block absolute top-8 h-px bg-gradient-to-r from-brand-500/40 to-brand-500/10"
                    // left: centre of this box → right: centre of next box
                    // We use left offset + full width minus half box width on each side
                    // Simpler: position from right edge of step number to left edge of next
                    // Using calc: starts at 50% + 32px (half of 64px icon), goes to end
                    // Tailwind can't express this cleanly, use inline style:
                    // width = 100% - 64px, left = 50% + 32px
                  />
                )}

                {/* Step number bubble */}
                <motion.div
                  whileHover={{ scale: 1.08 }}
                  whileInView={{ boxShadow: ["0 0 0 0 rgba(29,150,148,0)", "0 0 0 14px rgba(29,150,148,0.08)", "0 0 0 0 rgba(29,150,148,0)"] }}
                  viewport={{ once: false }}
                  transition={{ duration: 1.2, delay: i * 0.3 }}
                  className="w-16 h-16 rounded-2xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center mb-5 shrink-0 relative z-10"
                >
                  <span className="text-xl font-bold text-brand-500">{step.num}</span>
                </motion.div>

                <h3 className="font-semibold text-base text-[var(--text-primary)] mb-2">{step.title}</h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{step.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Example prompts ──────────────────────────────────────────────── */}
      <section className="py-24 px-6 bg-[var(--bg-surface)]">
        <div className="max-w-4xl mx-auto">

          <Reveal className="text-center mb-12 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">What can you ask?</h2>
            <p className="text-[var(--text-secondary)]">
              Anything you would ask a human analyst — just type it out.
            </p>
          </Reveal>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            className="grid grid-cols-1 sm:grid-cols-2 gap-3"
          >
            {EXAMPLES.map((ex) => (
              <motion.div
                key={ex}
                variants={fadeUp}
                whileHover={{ x: 4, borderColor: "rgba(29,150,148,0.4)" }}
                transition={{ type: "spring", stiffness: 400, damping: 25 }}
                className="flex items-center gap-3 px-5 py-4 rounded-xl bg-[var(--bg-base)] border border-[var(--border)] text-sm text-[var(--text-secondary)] cursor-default"
              >
                <motion.div
                  whileHover={{ scale: 1.2, rotate: -5 }}
                  className="shrink-0 text-brand-500"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </motion.div>
                <span>&ldquo;{ex}&rdquo;</span>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="py-28 px-6 relative overflow-hidden">
        {/* Background glow */}
        <motion.div
          animate={{ scale: [1, 1.2, 1], opacity: [0.4, 0.7, 0.4] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div className="w-[600px] h-[300px] bg-brand-500/8 rounded-full blur-3xl" />
        </motion.div>

        <div className="relative max-w-2xl mx-auto text-center">
          <Reveal className="space-y-6">
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight">
              Ready to analyse your data?
            </h2>
            <p className="text-[var(--text-secondary)] text-lg leading-relaxed">
              No setup, no code, no expertise needed. Just upload your file and
              start asking questions.
            </p>
            <motion.button
              whileHover={{ scale: 1.05, boxShadow: "0 24px 48px rgba(29,150,148,0.28)" }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              className="btn-primary text-base px-12 py-4 shadow-lg shadow-brand-500/20 relative overflow-hidden"
            >
              <motion.span
                animate={{ x: ["-100%", "200%"] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
                className="absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/20 to-transparent skew-x-12"
              />
              Start Analysing Now
            </motion.button>
          </Reveal>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
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
