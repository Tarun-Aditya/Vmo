const blue = { 50: "#F1F4FE", 100: "#E4EAFD", 200: "#C7D3FA", 300: "#9DB1F5", 400: "#6F8CFF", 500: "#3F62EB", 600: "#2347D9", 700: "#1C3AA8", 800: "#182F85", 900: "#142767", 950: "#0B1740" };
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"], darkMode: "class",
  theme: { extend: {
    colors: { indigo: blue, paper: "#EEF1F5", ink: { DEFAULT: "#0E1726", soft: "#1B2A44", mute: "#566275" }, line: "#D9DFE7" },
    fontFamily: { sans: ['"Inter Tight"', "system-ui", "sans-serif"], mono: ['"JetBrains Mono"', "ui-monospace", "monospace"], serif: ['"Inter Tight"', "system-ui", "sans-serif"] },
  } },
  plugins: [],
};
