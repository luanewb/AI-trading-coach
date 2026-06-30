import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#F8FAFC",
        bg: "#07090D",
        panel: "#10141D",
        elevated: "#151B26",
        line: "#263142",
        paper: "#0C1017",
        accent: "#2DD4BF",
        good: "#34D399",
        warn: "#FBBF24",
        bad: "#FB7185"
      }
    }
  },
  plugins: []
};

export default config;
