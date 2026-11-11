/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fintech: {
          25: '#f7fbff',
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          500: '#0284c7',
          600: '#0369a1',
          700: '#075985',
          800: '#0c4a6e',
          900: '#082f49',
          950: '#041c2c',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(4, 28, 44, 0.05), 0 1px 1px rgba(4, 28, 44, 0.03)',
        panel: '0 12px 32px -6px rgba(4, 28, 44, 0.14), 0 4px 10px -2px rgba(4, 28, 44, 0.06)',
      },
    },
  },
  plugins: [],
}
