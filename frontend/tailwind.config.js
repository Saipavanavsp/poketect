/** Palette: burgundy device shell, cream field-guide paper, warm-gray ink. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        shell: { DEFAULT: '#6B1A2A', dark: '#4A1220', light: '#8C2B3D' },
        paper: { DEFAULT: '#F1E6CC', soft: '#F7EFDC', edge: '#E2D3B0' },
        ink: { DEFAULT: '#3A3430', soft: '#5E5650', faint: '#8A8077' },
        stone: { DEFAULT: '#B9AFA3', light: '#D6CDC0', dark: '#6F665E' },
        lcd: { DEFAULT: '#C4BFA2', dark: '#8F8A6E', ink: '#2F3326' },
        led: '#E3A33B',
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Arial Narrow', 'sans-serif'],
        serif: ['"Source Serif 4"', 'Georgia', 'serif'],
      },
      boxShadow: {
        bezel: 'inset 0 2px 0 rgba(255,255,255,.12), inset 0 -3px 0 rgba(0,0,0,.25)',
        inset: 'inset 0 2px 6px rgba(47,51,38,.35)',
      },
    },
  },
  plugins: [],
}
