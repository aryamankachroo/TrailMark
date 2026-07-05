import type { Config } from "tailwindcss";

/**
 * TrailMark design language: federal court docket, not SaaS dashboard.
 * Dark navy ground, gold accents, hairline borders, tabular numerals.
 */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#060E1C",
          900: "#0A1628", // page ground
          850: "#0D1B31",
          800: "#0F1F38", // panels
          700: "#14284A", // raised surfaces
          600: "#1E3050", // hairline borders
          500: "#2A4067",
        },
        gold: {
          DEFAULT: "#C9A84C",
          bright: "#E3C670",
          dim: "#8F7836",
        },
        ink: {
          DEFAULT: "#E8EDF5", // primary text
          muted: "#8FA1BC", // secondary text
          faint: "#5A6B85",
        },
        verdict: {
          green: "#3C9A6E",
          amber: "#D9A03F",
          red: "#C25450",
          blue: "#5B8DD9",
        },
      },
      fontFamily: {
        display: ["Georgia", "Cambria", "'Times New Roman'", "serif"],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      letterSpacing: {
        docket: "0.14em",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
