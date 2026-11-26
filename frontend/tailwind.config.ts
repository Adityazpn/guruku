import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0B1F4B", 700: "#12306F", 50: "#F5F8FC" },
        accent: { DEFAULT: "#4DA3FF", 100: "#E6F2FF" },
      },
      fontFamily: { sans: ['"Inter Variable"', "Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
