/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#1e293b',   // auth app (unchanged)
        surface: '#334155',      // auth app (unchanged)
        paper: '#F7F3EC',
        card: '#FFFFFF',
        kraft: '#EFE7D8',
        line: '#E4DAC8',
        ink: '#241E1A',
        muted: '#5E564C',        // darkened from spec #6B6258 for AA safety on paper
        green: { DEFAULT: '#2E6B43', mid: '#3F8557', soft: '#E7F0E8' },
        paprika: { DEFAULT: '#DB5026', strong: '#B23E1C', soft: '#FBE6DC' },
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        body: ['"Hanken Grotesk"', 'system-ui', 'sans-serif'],
        price: ['"Space Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        '3xl': '1.5rem',
        '4xl': '2rem',
        '5xl': '2.5rem',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}