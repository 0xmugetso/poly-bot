/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: '#09090B',
        carbon: '#0D0D0D',
        accentGreen: '#10B981',
        accentCrimson: '#F43F5E',
        darkGray: '#1F2937',
      }
    },
  },
  plugins: [],
}
