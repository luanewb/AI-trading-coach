import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#151718",
        line: "#D9DFE3",
        paper: "#F6F7F4",
        good: "#157F4F",
        warn: "#B7791F",
        bad: "#B42318"
      }
    }
  },
  plugins: []
};

export default config;
