import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Paleta vigilancia-obstetrica (salud pública neutra, contraste AA)
        border: "hsl(220 13% 91%)",
        background: "hsl(0 0% 100%)",
        foreground: "hsl(222 47% 11%)",
        muted: "hsl(210 40% 96%)",
        "muted-foreground": "hsl(215 16% 47%)",
        primary: "hsl(222 47% 11%)",
        "primary-foreground": "hsl(210 40% 98%)",
        card: "hsl(0 0% 100%)",
        "card-foreground": "hsl(222 47% 11%)",
        // Risk tiers alineados con API (alto/medio/bajo)
        "risk-alto": "hsl(0 84% 45%)",
        "risk-medio": "hsl(38 92% 50%)",
        "risk-bajo": "hsl(142 71% 40%)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "0.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
