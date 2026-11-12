const teal = { 50: "#E9F4F1", 100: "#DCEFEA", 200: "#BFDDD6", 300: "#8CC4B8", 400: "#4FA595", 500: "#178273", 600: "#0E6B5E", 700: "#0B564B", 800: "#09453D", 900: "#073A33", 950: "#04211E" };
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"], darkMode: "class",
  theme: { extend: {
    colors: { indigo: teal, paper: "#F4F2EE", ink: { DEFAULT: "#1B1F24", soft: "#2A3038", mute: "#5E6670" }, line: "#E4E0D8" },
    fontFamily: { sans: ['"Instrument Sans"', "system-ui", "sans-serif"], serif: ["Newsreader", "Georgia", "serif"] },
  } },
  plugins: [],
};
