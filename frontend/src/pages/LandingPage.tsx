import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "@/hooks/useTheme";

// ── Animation variants ──────────────────────────────────────────────────────

const fadeUp = {
  hidden:  { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

const staggerContainer = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

const staggerFast = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.06 } },
};

// ── Data ───────────────────────────────────────────────────────────────────

const CAPABILITIES = [
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />,
    title: "Data Cleaning",
    desc:  "Fixes missing values, removes duplicates, corrects formatting, and standardises types — automatically.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />,
    title: "Exploratory Analysis",
    desc:  "Examines distributions, correlations, and unusual patterns to give you a thorough overview.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />,
    title: "Data Visualisation",
    desc:  "Generates charts, heatmaps, scatter plots, and dashboards — choosing the best format for your data.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />,
    title: "Statistical Analysis",
    desc:  "Runs hypothesis tests, regression, ANOVA, and confidence intervals with clear plain-English explanations.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />,
    title: "Predictive Analysis",
    desc:  "Builds forecasting models to predict future outcomes — sales, churn, trends — with accuracy metrics.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M10 21h7a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v11m0 5l4.879-4.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242z" />,
    title: "Diagnostic Analysis",
    desc:  "Investigates unexpected drops, spikes, or anomalies — isolating root causes and quantifying each factor.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />,
    title: "Prescriptive Analysis",
    desc:  "Recommends concrete actions ranked by likely impact, so you can make informed decisions immediately.",
  },
  {
    icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />,
    title: "Reporting",
    desc:  "Compiles findings into structured reports — executive summary, key takeaways, and detailed breakdowns.",
  },
];

const STEPS = [
  {
    num:   "01",
    title: "Upload your data",
    desc:  "Drop a CSV or Excel file. The AI reads it, identifies the structure, and cleans it automatically.",
  },
  {
    num:   "02",
    title: "Describe what you need",
    desc:  "Type your question in plain English. No code, no formulas, no technical knowledge required.",
  },
  {
    num:   "03",
    title: "Get your answer",
    desc:  "The AI analyses, generates charts and findings, and explains everything in a clear report.",
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

// ── Cycling prompt ──────────────────────────────────────────────────────────

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
          className="font-medium text-base sm:text-lg text-[#9E6975]"
        >
          &ldquo;{EXAMPLES[index]}&rdquo;
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ── Scroll-reveal wrapper ───────────────────────────────────────────────────

function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
      variants={fadeUp}
      transition={{ duration: 0.55, ease: "easeOut", delay }}
    >
      {children}
    </motion.div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";

  // Theme tokens
  const L = dark ? {
    bg:          "#0c0809",
    bgSurface:   "#110d0e",
    textPri:     "#f5ede8",
    textMut:     "#8a7a84",
    textDim:     "#4a3845",
    navBg:       "rgba(12,8,9,0.78)",
    navBorder:   "rgba(107,78,90,0.2)",
    badgeBg:     "rgba(107,78,90,0.18)",
    badgeBorder: "rgba(107,78,90,0.38)",
    cardBg:      "rgba(255,255,255,0.025)",
    cardBorder:  "rgba(107,78,90,0.1)",
    cardHover:   "rgba(255,255,255,0.05)",
    cardHoverBd: "rgba(107,78,90,0.3)",
    iconBg:      "rgba(107,78,90,0.15)",
    iconBorder:  "rgba(107,78,90,0.32)",
    orbBg1:      "radial-gradient(circle, rgba(107,78,90,0.22) 0%, rgba(107,78,90,0.06) 45%, transparent 70%)",
    orbBg2:      "radial-gradient(circle, rgba(158,105,117,0.18) 0%, transparent 70%)",
    scrollBd:    "rgba(107,78,90,0.4)",
    scrollDot:   "#6B4E5A",
    ctaGradient: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(107,78,90,0.14) 0%, transparent 70%)",
    footerBd:    "rgba(107,78,90,0.18)",
    toggleClr:   "#6B4E5A",
    toggleHover: "#9E6975",
  } : {
    bg:          "#e8dde1",
    bgSurface:   "#ddd1d6",
    textPri:     "#1a0f14",
    textMut:     "#5a3f4a",
    textDim:     "#8a6e78",
    navBg:       "rgba(232,221,225,0.88)",
    navBorder:   "rgba(107,78,90,0.2)",
    badgeBg:     "rgba(158,105,117,0.15)",
    badgeBorder: "rgba(158,105,117,0.35)",
    cardBg:      "rgba(255,255,255,0.5)",
    cardBorder:  "rgba(158,105,117,0.18)",
    cardHover:   "rgba(255,255,255,0.72)",
    cardHoverBd: "rgba(158,105,117,0.35)",
    iconBg:      "rgba(158,105,117,0.15)",
    iconBorder:  "rgba(158,105,117,0.32)",
    orbBg1:      "radial-gradient(circle, rgba(158,105,117,0.28) 0%, rgba(158,105,117,0.08) 45%, transparent 70%)",
    orbBg2:      "radial-gradient(circle, rgba(107,78,90,0.2) 0%, transparent 70%)",
    scrollBd:    "rgba(107,78,90,0.4)",
    scrollDot:   "#9E6975",
    ctaGradient: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(158,105,117,0.2) 0%, transparent 70%)",
    footerBd:    "rgba(107,78,90,0.2)",
    toggleClr:   "#9E6975",
    toggleHover: "#6B4E5A",
  };

  return (
    <div
      className="min-h-screen overflow-x-hidden font-sans"
      style={{ backgroundColor: L.bg, color: L.textPri }}
    >

      {/* ── Navigation ───────────────────────────────────────────────────── */}
      <nav
        className="fixed top-0 left-0 right-0 z-30 backdrop-blur-xl"
        style={{ backgroundColor: L.navBg, borderBottom: `1px solid ${L.navBorder}` }}
      >
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <motion.span
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-xl font-bold tracking-tight"
            style={{ color: L.textPri }}
          >
            Data<span className="text-[#9E6975]">Weaver</span>
          </motion.span>

          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="flex items-center gap-3"
          >
            <button
              onClick={toggle}
              className="w-9 h-9 rounded-xl flex items-center justify-center transition-colors"
              style={{ color: L.toggleClr }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = L.toggleHover)}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = L.toggleClr)}
            >
              {dark ? <SunIcon /> : <MoonIcon />}
            </button>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              className="text-sm px-5 py-2.5 rounded-xl font-medium text-white"
              style={{ backgroundColor: "#9E6975" }}
            >
              Launch App
            </motion.button>
          </motion.div>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-6 pt-16">

        {/* Blurred gradient orbs */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <motion.div
            animate={{ scale: [1, 1.12, 1], opacity: [0.8, 1, 0.8] }}
            transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
            style={{
              position: "absolute", top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              width: 900, height: 900, borderRadius: "50%",
              background: L.orbBg1,
              filter: "blur(60px)",
            }}
          />
          <motion.div
            animate={{ scale: [1, 1.18, 1], opacity: [0.6, 1, 0.6] }}
            transition={{ duration: 11, repeat: Infinity, ease: "easeInOut", delay: 2 }}
            style={{
              position: "absolute", top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              width: 550, height: 550, borderRadius: "50%",
              background: L.orbBg2,
              filter: "blur(50px)",
            }}
          />
        </div>

        {/* Hero content — centred */}
        <div className="relative max-w-4xl mx-auto text-center z-10">

          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full mb-8 text-[#c4a0af]"
            style={{ background: L.badgeBg, border: `1px solid ${L.badgeBorder}` }}
          >
            <motion.span
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 2.2, repeat: Infinity }}
            >
              ✦
            </motion.span>
            AI-powered data analysis
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={staggerFast}
            initial="hidden"
            animate="visible"
            className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1] mb-6"
          >
            {["Your", "personal"].map((word) => (
              <motion.span
                key={word}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="inline-block mr-[0.25em]"
                style={{ color: L.textPri }}
              >
                {word}
              </motion.span>
            ))}
            <br />
            {["AI", "data", "analyst"].map((word) => (
              <motion.span
                key={word}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="inline-block mr-[0.25em] text-[#9E6975]"
              >
                {word}
              </motion.span>
            ))}
          </motion.h1>

          {/* Subtext */}
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65 }}
            className="text-xl max-w-2xl mx-auto leading-relaxed mb-10"
            style={{ color: L.textMut }}
          >
            Upload any dataset and describe what you need in plain language.
            DataWeaver cleans, analyses, and visualises your data —
            giving you answers in seconds, not hours.
          </motion.p>

          {/* CTA */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.8 }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16"
          >
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              className="text-base px-9 py-4 rounded-xl font-medium text-white relative overflow-hidden"
              style={{ backgroundColor: "#9E6975", boxShadow: "0 12px 32px rgba(158,105,117,0.35)" }}
            >
              <motion.span
                animate={{ x: ["-100%", "200%"] }}
                transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 1.5 }}
                className="absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/15 to-transparent skew-x-12"
              />
              Start Analysing — it&apos;s free
            </motion.button>
            <p className="text-sm" style={{ color: L.textDim }}>
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
            <p className="text-xs uppercase tracking-widest" style={{ color: L.textDim }}>
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
            className="w-5 h-8 rounded-full flex items-start justify-center pt-1.5"
            style={{ border: `2px solid ${L.scrollBd}` }}
          >
            <div className="w-1 h-2 rounded-full" style={{ background: L.scrollDot }} />
          </motion.div>
          <p className="text-[10px] tracking-widest uppercase" style={{ color: L.textDim }}>Scroll</p>
        </motion.div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="py-24 px-6" style={{ backgroundColor: L.bgSurface }}>
        <div className="max-w-4xl mx-auto">

          <Reveal className="text-center mb-16 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight" style={{ color: L.textPri }}>
              How it works
            </h2>
            <p style={{ color: L.textMut }}>Three steps from raw data to clear answers.</p>
          </Reveal>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 md:grid-cols-3 gap-8"
          >
            {STEPS.map((step) => (
              <motion.div
                key={step.num}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                className="flex flex-col items-center text-center"
              >
                <motion.div
                  whileHover={{ scale: 1.06 }}
                  className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 shrink-0"
                  style={{ background: L.iconBg, border: `1px solid ${L.iconBorder}` }}
                >
                  <span className="text-xl font-bold text-[#9E6975]">{step.num}</span>
                </motion.div>
                <h3 className="font-semibold text-base mb-2" style={{ color: L.textPri }}>{step.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: L.textMut }}>{step.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Capabilities ─────────────────────────────────────────────────── */}
      <section className="py-24 px-6" style={{ backgroundColor: L.bg }}>
        <div className="max-w-6xl mx-auto">

          <Reveal className="text-center mb-16 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight" style={{ color: L.textPri }}>
              Everything you need from an analyst
            </h2>
            <p className="max-w-xl mx-auto" style={{ color: L.textMut }}>
              DataWeaver handles the full analysis pipeline — from raw data to actionable insights.
            </p>
          </Reveal>

          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
          >
            {CAPABILITIES.map((cap) => (
              <motion.div
                key={cap.title}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                whileHover={{ y: -4 }}
                className="group p-5 rounded-2xl cursor-default transition-all"
                style={{ background: L.cardBg, border: `1px solid ${L.cardBorder}` }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = L.cardHover;
                  (e.currentTarget as HTMLElement).style.borderColor = L.cardHoverBd;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = L.cardBg;
                  (e.currentTarget as HTMLElement).style.borderColor = L.cardBorder;
                }}
              >
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: L.iconBg }}
                >
                  <svg className="w-5 h-5 text-[#9E6975]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    {cap.icon}
                  </svg>
                </div>
                <h3 className="font-semibold text-sm mb-1.5" style={{ color: L.textPri }}>{cap.title}</h3>
                <p className="text-xs leading-relaxed" style={{ color: L.textMut }}>{cap.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Example prompts ──────────────────────────────────────────────── */}
      <section className="py-24 px-6" style={{ backgroundColor: L.bgSurface }}>
        <div className="max-w-4xl mx-auto">

          <Reveal className="text-center mb-12 space-y-3">
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight" style={{ color: L.textPri }}>
              What can you ask?
            </h2>
            <p style={{ color: L.textMut }}>
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
                transition={{ duration: 0.5, ease: "easeOut" }}
                whileHover={{ x: 4 }}
                className="flex items-center gap-3 px-5 py-4 rounded-xl text-sm cursor-default transition-all"
                style={{ background: L.cardBg, border: `1px solid ${L.cardBorder}`, color: L.textMut }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = L.cardHover;
                  (e.currentTarget as HTMLElement).style.borderColor = L.cardHoverBd;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = L.cardBg;
                  (e.currentTarget as HTMLElement).style.borderColor = L.cardBorder;
                }}
              >
                <svg className="w-4 h-4 shrink-0 text-[#9E6975]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span>&ldquo;{ex}&rdquo;</span>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="py-28 px-6 relative overflow-hidden" style={{ backgroundColor: L.bg }}>
        <div className="absolute inset-0 pointer-events-none" style={{ background: L.ctaGradient }} />
        <div className="relative max-w-2xl mx-auto text-center">
          <Reveal className="space-y-6">
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight" style={{ color: L.textPri }}>
              Ready to analyse your data?
            </h2>
            <p className="text-lg leading-relaxed" style={{ color: L.textMut }}>
              No setup, no code, no expertise needed. Just upload your file and
              start asking questions.
            </p>
            <div>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate("/chat")}
                className="text-base px-12 py-4 rounded-xl font-medium text-white relative overflow-hidden"
                style={{ backgroundColor: "#9E6975", boxShadow: "0 16px 40px rgba(158,105,117,0.35)" }}
              >
                <motion.span
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
                  className="absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/15 to-transparent skew-x-12"
                />
                Start Analysing Now
              </motion.button>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer
        className="py-8 px-6"
        style={{ backgroundColor: L.bgSurface, borderTop: `1px solid ${L.footerBd}` }}
      >
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-sm font-semibold" style={{ color: L.textPri }}>
            Data<span className="text-[#9E6975]">Weaver</span>
          </span>
          <p className="text-xs" style={{ color: L.textDim }}>
            AI-powered data analysis · Upload · Ask · Understand
          </p>
        </div>
      </footer>
    </div>
  );
}

// ── Icons ──────────────────────────────────────────────────────────────────

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
