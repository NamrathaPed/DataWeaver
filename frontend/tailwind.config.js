/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#e8f7f7",
          100: "#c5eceb",
          200: "#9ededd",
          300: "#6dcfce",
          400: "#42c2c0",
          500: "#1d9694",
          600: "#177978",
          700: "#115c5b",
          800: "#0b3f3e",
          900: "#052221",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace"],
      },
      keyframes: {
        fadeSlideUp: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
      },
      animation: {
        "fade-up": "fadeSlideUp 0.18s ease-out forwards",
        blink: "blink 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
