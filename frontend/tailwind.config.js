/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0F0F1A",
        card: "#1A1A2E",
        accent: "#4F46E5"
      }
    }
  },
  plugins: []
};

