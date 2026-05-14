import { useState, useEffect, useRef, useCallback, memo } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import Particles from "react-tsparticles";
import { loadSlim } from "tsparticles-slim";
import type { Engine } from "tsparticles-engine";
import * as THREE from "three";

// ── Design tokens (rose palette) ────────────────────────────────────────────

const R = {
  accent:      "#9E6975",
  accentDim:   "rgba(158,105,117,0.62)",
  accentFaint: "rgba(158,105,117,0.12)",
  accentGlow:  "rgba(158,105,117,0.35)",
  bg:          "#080810",
  bgAlt:       "#09090f",
  textPri:     "#e2e2e8",
  textMut:     "rgba(226,226,232,0.62)",
  textSub:     "rgba(226,226,232,0.48)",
  border:      "rgba(255,255,255,0.04)",
  navBg:       "rgba(8,8,16,0.55)",
  cardBg:      "rgba(255,255,255,0.03)",
  cardBorder:  "rgba(158,105,117,0.08)",
  cardHoverBg: "rgba(255,255,255,0.055)",
  cardHoverBd: "rgba(158,105,117,0.28)",
  iconBg:      "rgba(158,105,117,0.1)",
  iconBorder:  "rgba(158,105,117,0.2)",
};

// ── Animation variants ──────────────────────────────────────────────────────

const fadeUp = {
  hidden:  { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0 },
};

const stagger = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.09, delayChildren: 0.1 } },
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

// ── Particle background — memoised to prevent re-render flicker ─────────────

const ParticleBackground = memo(() => {
  const init = useCallback(async (engine: Engine) => {
    await loadSlim(engine);
  }, []);

  return (
    <Particles
      id="hero-particles"
      init={init}
      style={{ position: "absolute", inset: 0, zIndex: 0 }}
      options={{
        background: { color: { value: "transparent" } },
        fpsLimit: 60,
        particles: {
          number:  { value: 90, density: { enable: true, area: 900 } },
          color:   { value: "#9E6975" },
          opacity: { value: 0.85 },
          size:    { value: { min: 1.5, max: 3 } },
          move:    { enable: true, speed: 0.6, direction: "none", random: true, outModes: "bounce" },
          links:   { enable: true, distance: 130, color: "#9E6975", opacity: 0.25, width: 1 },
        },
        interactivity: {
          events:  { onHover: { enable: true, mode: "repulse" } },
          modes:   { repulse: { distance: 80, duration: 2, speed: 0.3 } },
        },
        detectRetina: true,
      }}
    />
  );
});

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
          style={{ color: R.accent, fontFamily: "'JetBrains Mono', monospace", fontSize: "0.875rem" }}
        >
          &ldquo;{EXAMPLES[index]}&rdquo;
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// ── Section label (// 01 — name) ────────────────────────────────────────────

function SectionLabel({ n, name }: { n: string; name: string }) {
  return (
    <p
      style={{
        fontFamily:    "'JetBrains Mono', monospace",
        fontSize:      "0.7rem",
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        color:         R.accent,
        textShadow:    `0 0 20px rgba(158,105,117,0.6)`,
        marginBottom:  "1rem",
      }}
    >
      // {n} — {name}
    </p>
  );
}

// ── Section heading with gradient underline ─────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "inline-block" }}>
      <h2
        style={{
          fontFamily:    "'Inter', ui-sans-serif, system-ui",
          fontWeight:    800,
          letterSpacing: "-0.03em",
          color:         R.textPri,
          fontSize:      "clamp(1.75rem, 4vw, 2.5rem)",
          lineHeight:    1.1,
          marginBottom:  "0.6rem",
        }}
      >
        {children}
      </h2>
      <div
        style={{
          width:      "48px",
          height:     "3px",
          background: `linear-gradient(90deg, ${R.accent}, transparent)`,
          boxShadow:  `0 0 8px rgba(158,105,117,0.5)`,
          borderRadius: "2px",
        }}
      />
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

// ── Three.js icosahedron (hero right panel) ────────────────────────────────

function IcosahedronScene() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const W = mount.clientWidth  || 400;
    const H = mount.clientHeight || 400;

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    camera.position.z = 3.6;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const geo = new THREE.IcosahedronGeometry(1.3, 0);
    const fillMesh = new THREE.Mesh(geo,
      new THREE.MeshBasicMaterial({ color: 0x6B4E5A, transparent: true, opacity: 0.07 })
    );
    const wireMesh = new THREE.Mesh(geo,
      new THREE.MeshBasicMaterial({ color: 0xc4a0af, wireframe: true, transparent: true, opacity: 0.95 })
    );
    const haloMesh = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.38, 0),
      new THREE.MeshBasicMaterial({ color: 0x9E6975, wireframe: true, transparent: true, opacity: 0.12 })
    );

    // Vertex dots — bright points at each of the 12 icosahedron corners
    const pointsMesh = new THREE.Points(
      geo,
      new THREE.PointsMaterial({ color: 0xc4a0af, size: 0.08, transparent: true, opacity: 1 })
    );

    scene.add(fillMesh, wireMesh, haloMesh, pointsMesh);

    // Mouse target — normalised -1..1 relative to the canvas
    let targetX = 0;
    let targetY = 0;

    const onMouseMove = (e: MouseEvent) => {
      const rect = mount.getBoundingClientRect();
      targetX = ((e.clientX - rect.left) / rect.width  - 0.5) * 2;
      targetY = ((e.clientY - rect.top)  / rect.height - 0.5) * 2;
    };
    // Listen on the whole section so cursor anywhere in hero drives it
    const section = mount.closest("section") ?? mount;
    section.addEventListener("mousemove", onMouseMove);

    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      // Base auto-rotation
      wireMesh.rotation.x += 0.003;
      wireMesh.rotation.y += 0.005;
      // Smooth lerp toward cursor influence
      wireMesh.rotation.x += (targetY * 0.4 - wireMesh.rotation.x % (Math.PI * 2)) * 0.02;
      wireMesh.rotation.y += (targetX * 0.6 - wireMesh.rotation.y % (Math.PI * 2)) * 0.02;
      fillMesh.rotation.x   = wireMesh.rotation.x;
      fillMesh.rotation.y   = wireMesh.rotation.y;
      pointsMesh.rotation.x = wireMesh.rotation.x;
      pointsMesh.rotation.y = wireMesh.rotation.y;
      haloMesh.rotation.x   = wireMesh.rotation.x * 0.8;
      haloMesh.rotation.y   = wireMesh.rotation.y * 0.8;
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      const W2 = mount.clientWidth;
      const H2 = mount.clientHeight;
      if (!W2 || !H2) return;
      camera.aspect = W2 / H2;
      camera.updateProjectionMatrix();
      renderer.setSize(W2, H2);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", onResize);
      section.removeEventListener("mousemove", onMouseMove);
      renderer.dispose();
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div
      ref={mountRef}
      style={{
        width:  "100%",
        height: "420px",
        filter: "drop-shadow(0 0 24px rgba(158,105,117,0.35))",
      }}
    />
  );
}

// ── Hamburger Menu ──────────────────────────────────────────────────────────

function HamburgerMenu({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="sm:hidden flex flex-col gap-1.5 p-2"
      aria-label="Open menu"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            display:      "block",
            width:        "20px",
            height:       "2px",
            background:   R.textMut,
            borderRadius: "1px",
          }}
        />
      ))}
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const sectionPad = "clamp(5rem,10vw,8rem) clamp(2rem,8vw,7rem)";

  return (
    <div
      style={{
        minHeight:   "100vh",
        overflowX:   "hidden",
        background:  R.bg,
        color:       R.textPri,
        fontFamily:  "'Inter', ui-sans-serif, system-ui",
      }}
    >

      {/* ── Navbar ─────────────────────────────────────────────────────────── */}
      <nav
        style={{
          position:       "fixed",
          top:            0,
          left:           0,
          right:          0,
          zIndex:         30,
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          background:     R.navBg,
          borderBottom:   `1px solid rgba(255,255,255,0.06)`,
        }}
      >
        <div
          style={{
            maxWidth:  "1200px",
            margin:    "0 auto",
            padding:   "0 1.5rem",
            height:    "4rem",
            display:   "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <motion.span
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            style={{
              fontFamily:    "'Inter', ui-sans-serif, system-ui",
              fontWeight:    800,
              fontSize:      "1.2rem",
              letterSpacing: "-0.02em",
              color:         R.textPri,
            }}
          >
            Data<span style={{ color: R.accent }}>Weaver</span>
          </motion.span>

          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            style={{ display: "flex", alignItems: "center", gap: "1rem" }}
          >
            <HamburgerMenu onClick={() => setMenuOpen(!menuOpen)} />
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/chat")}
              style={{
                display:         "none",
                fontSize:        "0.875rem",
                padding:         "0.6rem 1.25rem",
                borderRadius:    "0.75rem",
                fontWeight:      500,
                color:           "#fff",
                background:      R.accent,
                border:          "none",
                cursor:          "pointer",
                boxShadow:       `0 0 20px rgba(158,105,117,0.25)`,
              }}
              className="sm:!block"
            >
              Launch App
            </motion.button>
          </motion.div>
        </div>

        {/* Mobile menu */}
        <AnimatePresence>
          {menuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              style={{
                borderTop: `1px solid ${R.border}`,
                padding:   "1rem 1.5rem",
              }}
            >
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={() => { navigate("/chat"); setMenuOpen(false); }}
                style={{
                  width:        "100%",
                  padding:      "0.75rem",
                  borderRadius: "0.75rem",
                  fontWeight:   500,
                  color:        "#fff",
                  background:   R.accent,
                  border:       "none",
                  cursor:       "pointer",
                }}
              >
                Launch App
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <section
        style={{
          position:  "relative",
          minHeight: "100vh",
          display:   "flex",
          alignItems: "center",
          overflow:  "hidden",
          paddingTop: "4rem",
          background: R.bg,
        }}
      >
        <ParticleBackground />

        {/* Ambient radial glow — bottom-left */}
        <div
          style={{
            position:   "absolute",
            inset:      0,
            background: "radial-gradient(ellipse 60% 55% at 10% 90%, rgba(158,105,117,0.1) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        <div
          style={{
            position:      "relative",
            zIndex:        1,
            maxWidth:      "1200px",
            margin:        "0 auto",
            padding:       "0 clamp(1.5rem,6vw,5rem)",
            display:       "grid",
            gridTemplateColumns: "1fr 1fr",
            gap:           "3rem",
            alignItems:    "center",
            width:         "100%",
            pointerEvents: "none",
          }}
          className="hero-grid"
        >
          {/* Left — text (re-enable pointer events for clicks/selection) */}
          <div style={{ pointerEvents: "auto" }}>
            {/* Badge */}
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: -8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              style={{
                display:       "inline-flex",
                alignItems:    "center",
                gap:           "0.5rem",
                fontSize:      "0.7rem",
                fontWeight:    500,
                padding:       "0.35rem 0.9rem",
                borderRadius:  "999px",
                marginBottom:  "1.75rem",
                color:         R.accentDim,
                background:    "rgba(158,105,117,0.08)",
                border:        `1px solid rgba(158,105,117,0.2)`,
                fontFamily:    "'JetBrains Mono', monospace",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
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
              variants={stagger}
              initial="hidden"
              animate="visible"
              style={{
                fontFamily:    "'Inter', ui-sans-serif, system-ui",
                fontWeight:    800,
                letterSpacing: "-0.03em",
                lineHeight:    1.08,
                fontSize:      "clamp(2.5rem, 5.5vw, 4.5rem)",
                marginBottom:  "1.25rem",
              }}
            >
              {["Your", "personal"].map((w) => (
                <motion.span
                  key={w}
                  variants={fadeUp}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                  style={{ display: "inline-block", marginRight: "0.25em", color: R.textPri }}
                >
                  {w}
                </motion.span>
              ))}
              <br />
              {["AI", "data", "analyst"].map((w) => (
                <motion.span
                  key={w}
                  variants={fadeUp}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                  style={{
                    display:    "inline-block",
                    marginRight: "0.25em",
                    color:      R.accent,
                    textShadow: `0 0 30px rgba(158,105,117,0.4)`,
                  }}
                >
                  {w}
                </motion.span>
              ))}
            </motion.h1>

            {/* Subtext */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.65 }}
              style={{
                fontSize:     "1.1rem",
                lineHeight:   1.7,
                marginBottom: "2rem",
                color:        R.textMut,
                maxWidth:     "38ch",
              }}
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
              style={{ display: "flex", flexWrap: "wrap", gap: "1rem", marginBottom: "2.5rem" }}
            >
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate("/chat")}
                style={{
                  fontSize:     "0.95rem",
                  padding:      "0.85rem 2rem",
                  borderRadius: "0.75rem",
                  fontWeight:   600,
                  color:        "#fff",
                  background:   R.accent,
                  border:       "none",
                  cursor:       "pointer",
                  position:     "relative",
                  overflow:     "hidden",
                  boxShadow:    `0 12px 32px rgba(158,105,117,0.35)`,
                }}
              >
                <motion.span
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 1.5 }}
                  style={{
                    position:   "absolute",
                    inset:      0,
                    width:      "33%",
                    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)",
                    transform:  "skewX(-12deg)",
                  }}
                />
                Start Analysing — it&apos;s free
              </motion.button>
              <p style={{ fontSize: "0.8rem", color: R.textSub, alignSelf: "center" }}>
                No account required · CSV &amp; Excel supported
              </p>
            </motion.div>

            {/* Cycling prompt */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1.1, duration: 0.6 }}
            >
              <p
                style={{
                  fontSize:      "0.65rem",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color:         R.textSub,
                  marginBottom:  "0.4rem",
                  fontFamily:    "'JetBrains Mono', monospace",
                }}
              >
                People are asking
              </p>
              <CyclingPrompt />
            </motion.div>
          </div>

          {/* Right — animated data orb */}
          <motion.div
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
            style={{ display: "flex", justifyContent: "center", pointerEvents: "auto" }}
            className="hero-orb"
          >
            <IcosahedronScene />
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.6, duration: 0.6 }}
          style={{
            position:       "absolute",
            bottom:         "2.5rem",
            left:           "50%",
            transform:      "translateX(-50%)",
            display:        "flex",
            flexDirection:  "column",
            alignItems:     "center",
            gap:            "0.25rem",
          }}
        >
          <motion.div
            animate={{ y: [0, 8, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            style={{
              width:        "1.25rem",
              height:       "2rem",
              borderRadius: "999px",
              border:       `2px solid rgba(158,105,117,0.4)`,
              display:      "flex",
              alignItems:   "flex-start",
              justifyContent: "center",
              paddingTop:   "0.35rem",
            }}
          >
            <div
              style={{
                width:        "0.25rem",
                height:       "0.5rem",
                borderRadius: "999px",
                background:   R.accent,
              }}
            />
          </motion.div>
          <p
            style={{
              fontSize:      "0.6rem",
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color:         R.textSub,
              fontFamily:    "'JetBrains Mono', monospace",
            }}
          >
            Scroll
          </p>
        </motion.div>
      </section>

      {/* ── How it works ───────────────────────────────────────────────────── */}
      <section
        style={{
          background:  R.bgAlt,
          padding:     sectionPad,
          borderTop:   `1px solid ${R.border}`,
          position:    "relative",
          overflow:    "hidden",
        }}
      >
        <div
          style={{
            position:   "absolute",
            inset:      0,
            background: "radial-gradient(ellipse 50% 60% at 90% 20%, rgba(158,105,117,0.07) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{ maxWidth: "1000px", margin: "0 auto", position: "relative" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "3.5rem" }}>
              <SectionLabel n="02" name="how-it-works" />
              <SectionHeading>How it works</SectionHeading>
              <p style={{ color: R.textMut, marginTop: "0.8rem", maxWidth: "40ch", margin: "0.8rem auto 0" }}>
                Three steps from raw data to clear answers.
              </p>
            </div>
          </Reveal>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            style={{
              display:             "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
              gap:                 "1.5rem",
            }}
          >
            {STEPS.map((step) => (
              <motion.div
                key={step.num}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                style={{
                  display:      "flex",
                  flexDirection: "column",
                  alignItems:   "center",
                  textAlign:    "center",
                  padding:      "2rem 1.5rem",
                  borderRadius: "1.25rem",
                  background:   R.cardBg,
                  border:       `1px solid ${R.cardBorder}`,
                  boxShadow:    `0 0 10px ${R.accentFaint}`,
                  transition:   "all 0.25s ease",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.boxShadow = `0 0 20px ${R.accentGlow}, 0 0 50px ${R.accentFaint}`;
                  (e.currentTarget as HTMLElement).style.borderColor = "rgba(158,105,117,0.35)";
                  (e.currentTarget as HTMLElement).style.borderTopColor = R.accent;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.boxShadow = `0 0 10px ${R.accentFaint}`;
                  (e.currentTarget as HTMLElement).style.borderColor = R.cardBorder;
                  (e.currentTarget as HTMLElement).style.borderTopColor = R.cardBorder;
                }}
              >
                <motion.div
                  whileHover={{ scale: 1.06 }}
                  style={{
                    width:        "3.5rem",
                    height:       "3.5rem",
                    borderRadius: "1rem",
                    display:      "flex",
                    alignItems:   "center",
                    justifyContent: "center",
                    marginBottom: "1.25rem",
                    background:   R.iconBg,
                    border:       `1px solid ${R.iconBorder}`,
                  }}
                >
                  <span
                    style={{
                      fontFamily:    "'JetBrains Mono', monospace",
                      fontWeight:    700,
                      fontSize:      "1rem",
                      color:         R.accent,
                      textShadow:    `0 0 10px rgba(158,105,117,0.5)`,
                    }}
                  >
                    {step.num}
                  </span>
                </motion.div>
                <h3
                  style={{
                    fontFamily:  "'Inter', ui-sans-serif, system-ui",
                    fontWeight:  700,
                    fontSize:    "1rem",
                    marginBottom: "0.5rem",
                    color:       R.textPri,
                  }}
                >
                  {step.title}
                </h3>
                <p style={{ fontSize: "0.875rem", lineHeight: 1.65, color: R.textMut }}>
                  {step.desc}
                </p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Capabilities ───────────────────────────────────────────────────── */}
      <section
        style={{
          background:  R.bg,
          padding:     sectionPad,
          borderTop:   `1px solid ${R.border}`,
          position:    "relative",
          overflow:    "hidden",
        }}
      >
        <div
          style={{
            position:   "absolute",
            inset:      0,
            background: "radial-gradient(ellipse 55% 50% at 5% 50%, rgba(158,105,117,0.07) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{ maxWidth: "1200px", margin: "0 auto", position: "relative" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "3.5rem" }}>
              <SectionLabel n="03" name="capabilities" />
              <SectionHeading>Everything you need from an analyst</SectionHeading>
              <p style={{ color: R.textMut, marginTop: "0.8rem", maxWidth: "48ch", margin: "0.8rem auto 0" }}>
                DataWeaver handles the full analysis pipeline — from raw data to actionable insights.
              </p>
            </div>
          </Reveal>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            style={{
              display:             "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))",
              gap:                 "1rem",
            }}
          >
            {CAPABILITIES.map((cap) => (
              <motion.div
                key={cap.title}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                whileHover={{ y: -4 }}
                style={{
                  padding:      "1.25rem",
                  borderRadius: "1rem",
                  background:   R.cardBg,
                  border:       `1px solid ${R.cardBorder}`,
                  boxShadow:    `0 0 10px ${R.accentFaint}`,
                  cursor:       "default",
                  transition:   "all 0.25s ease",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background   = R.cardHoverBg;
                  (e.currentTarget as HTMLElement).style.borderColor  = "rgba(158,105,117,0.28)";
                  (e.currentTarget as HTMLElement).style.borderTopColor = R.accent;
                  (e.currentTarget as HTMLElement).style.boxShadow   = `0 0 20px ${R.accentGlow}, 0 0 50px ${R.accentFaint}`;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background   = R.cardBg;
                  (e.currentTarget as HTMLElement).style.borderColor  = R.cardBorder;
                  (e.currentTarget as HTMLElement).style.borderTopColor = R.cardBorder;
                  (e.currentTarget as HTMLElement).style.boxShadow   = `0 0 10px ${R.accentFaint}`;
                }}
              >
                <div
                  style={{
                    width:        "2.5rem",
                    height:       "2.5rem",
                    borderRadius: "0.75rem",
                    display:      "flex",
                    alignItems:   "center",
                    justifyContent: "center",
                    marginBottom: "0.9rem",
                    background:   R.iconBg,
                    border:       `1px solid ${R.iconBorder}`,
                  }}
                >
                  <svg
                    style={{ width: "1.1rem", height: "1.1rem", color: R.accent }}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    {cap.icon}
                  </svg>
                </div>
                <h3
                  style={{
                    fontFamily:  "'Inter', ui-sans-serif, system-ui",
                    fontWeight:  700,
                    fontSize:    "0.875rem",
                    marginBottom: "0.4rem",
                    color:       R.textPri,
                  }}
                >
                  {cap.title}
                </h3>
                <p style={{ fontSize: "0.78rem", lineHeight: 1.6, color: R.textMut }}>
                  {cap.desc}
                </p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Example prompts ────────────────────────────────────────────────── */}
      <section
        style={{
          background:  R.bgAlt,
          padding:     sectionPad,
          borderTop:   `1px solid ${R.border}`,
          position:    "relative",
          overflow:    "hidden",
        }}
      >
        <div
          style={{
            position:   "absolute",
            inset:      0,
            background: "radial-gradient(ellipse 50% 55% at 95% 80%, rgba(158,105,117,0.07) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{ maxWidth: "1000px", margin: "0 auto", position: "relative" }}>
          <Reveal>
            <div style={{ textAlign: "center", marginBottom: "3rem" }}>
              <SectionLabel n="04" name="what-you-can-ask" />
              <SectionHeading>What can you ask?</SectionHeading>
              <p style={{ color: R.textMut, marginTop: "0.8rem" }}>
                Anything you would ask a human analyst — just type it out.
              </p>
            </div>
          </Reveal>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            style={{
              display:             "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))",
              gap:                 "0.75rem",
            }}
          >
            {EXAMPLES.map((ex) => (
              <motion.div
                key={ex}
                variants={fadeUp}
                transition={{ duration: 0.5, ease: "easeOut" }}
                whileHover={{ x: 4 }}
                style={{
                  display:      "flex",
                  alignItems:   "center",
                  gap:          "0.75rem",
                  padding:      "1rem 1.25rem",
                  borderRadius: "0.75rem",
                  fontSize:     "0.875rem",
                  cursor:       "default",
                  background:   R.cardBg,
                  border:       `1px solid ${R.cardBorder}`,
                  color:        R.textMut,
                  boxShadow:    `0 0 10px ${R.accentFaint}`,
                  transition:   "all 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background   = R.cardHoverBg;
                  (e.currentTarget as HTMLElement).style.borderColor  = R.cardHoverBd;
                  (e.currentTarget as HTMLElement).style.boxShadow   = `0 0 20px ${R.accentGlow}, 0 0 50px ${R.accentFaint}`;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background   = R.cardBg;
                  (e.currentTarget as HTMLElement).style.borderColor  = R.cardBorder;
                  (e.currentTarget as HTMLElement).style.boxShadow   = `0 0 10px ${R.accentFaint}`;
                }}
              >
                <svg
                  style={{ width: "1rem", height: "1rem", flexShrink: 0, color: R.accent }}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span>&ldquo;{ex}&rdquo;</span>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Final CTA ──────────────────────────────────────────────────────── */}
      <section
        style={{
          background:  R.bg,
          padding:     sectionPad,
          borderTop:   `1px solid ${R.border}`,
          position:    "relative",
          overflow:    "hidden",
        }}
      >
        <div
          style={{
            position:   "absolute",
            inset:      0,
            background: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(158,105,117,0.08) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{ maxWidth: "640px", margin: "0 auto", textAlign: "center", position: "relative" }}>
          <Reveal>
            <div>
              <SectionLabel n="05" name="get-started" />
              <SectionHeading>Ready to analyse your data?</SectionHeading>
              <p
                style={{
                  fontSize:    "1.05rem",
                  lineHeight:  1.7,
                  color:       R.textMut,
                  margin:      "1.25rem 0 2rem",
                }}
              >
                No setup, no code, no expertise needed. Just upload your file and
                start asking questions.
              </p>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => navigate("/chat")}
                style={{
                  fontSize:     "0.95rem",
                  padding:      "1rem 3rem",
                  borderRadius: "0.75rem",
                  fontWeight:   600,
                  color:        "#fff",
                  background:   R.accent,
                  border:       "none",
                  cursor:       "pointer",
                  position:     "relative",
                  overflow:     "hidden",
                  boxShadow:    `0 16px 40px rgba(158,105,117,0.35)`,
                }}
              >
                <motion.span
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 2.5, repeat: Infinity, ease: "linear", repeatDelay: 2 }}
                  style={{
                    position:   "absolute",
                    inset:      0,
                    width:      "33%",
                    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)",
                    transform:  "skewX(-12deg)",
                  }}
                />
                Start Analysing Now
              </motion.button>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer
        style={{
          background:  R.bgAlt,
          borderTop:   `1px solid ${R.border}`,
          padding:     "2rem clamp(1.5rem,6vw,5rem)",
        }}
      >
        <div
          style={{
            maxWidth:      "1200px",
            margin:        "0 auto",
            display:       "flex",
            flexWrap:      "wrap",
            alignItems:    "center",
            justifyContent: "space-between",
            gap:           "1rem",
          }}
        >
          <span
            style={{
              fontFamily:    "'Inter', ui-sans-serif, system-ui",
              fontWeight:    800,
              fontSize:      "1rem",
              letterSpacing: "-0.02em",
              color:         R.textPri,
            }}
          >
            Data<span style={{ color: R.accent }}>Weaver</span>
          </span>
          <p
            style={{
              fontSize:  "0.75rem",
              color:     R.textSub,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            AI-powered data analysis · Upload · Ask · Understand
          </p>
        </div>
      </footer>

      {/* ── Responsive styles ──────────────────────────────────────────────── */}
      <style>{`
        @media (max-width: 768px) {
          .hero-grid {
            grid-template-columns: 1fr !important;
          }
          .hero-orb {
            position: absolute !important;
            inset: 0;
            opacity: 0.15;
            pointer-events: none;
          }
        }
        @media (min-width: 640px) {
          button.sm\\:\\!block {
            display: block !important;
          }
        }
        @media (max-width: 600px) {
          .cap-grid > div {
            min-width: 66px !important;
          }
        }
      `}</style>
    </div>
  );
}
