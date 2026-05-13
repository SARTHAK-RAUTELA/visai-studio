/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        'app-bg': '#0a0a0f',
        'card-bg': '#12121a',
        'card-border': '#1e1e2e',
      },
      backgroundImage: {
        'violet-gradient': 'linear-gradient(135deg, #7c3aed, #6d28d9)',
      },
    },
  },
  plugins: [],
}
