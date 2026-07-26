/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './new-components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"SF Pro Text"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        mono: ['"SF Mono"', '"JetBrains Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        // 四级字号体系：辅助/正文/标题/页面标题
        aux: ['12px', { lineHeight: '1.5' }],
        body: ['13px', { lineHeight: '1.6' }],
        title: ['14px', { lineHeight: '1.5', fontWeight: '500' }],
        head: ['16px', { lineHeight: '1.4', fontWeight: '600' }],
        page: ['18px', { lineHeight: '1.35', fontWeight: '600' }],
      },
      colors: {
        brand: {
          DEFAULT: '#4f46e5',
          hover: '#6366f1',
          active: '#4338ca',
          soft: '#eef0fe',
        },
        ink: {
          900: '#14161c',
          700: '#3b4154',
          500: '#5d6577',
          400: '#8a92a6',
          300: '#b4bac8',
        },
        line: {
          DEFAULT: '#e5e8ef',
          soft: '#eff1f6',
        },
        surface: {
          page: '#f7f8fa',
          fill: '#f2f4f8',
          elev: '#ffffff',
        },
        theme: {
          primary: '#4f46e5',
          light: '#f7f8fa',
          dark: '#151622',
          'dark-container': '#232734',
          success: '#22c55e',
          error: '#ef4444',
          warning: '#f59e0b',
        },
        gradientL: '#00DAEF',
        gradientR: '#4f46e5',
      },
      borderRadius: {
        xs: '6px',
        sm: '8px',
        md: '10px',
        lg: '14px',
        xl: '20px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04)',
        pop: '0 4px 16px rgba(16, 24, 40, 0.08)',
        modal: '0 12px 40px rgba(16, 24, 40, 0.12)',
        glow: '0 0 0 4px rgba(79, 70, 229, 0.08)',
      },
      backgroundColor: {
        bar: '#e0e7f2',
      },
      textColor: {
        default: '#4f46e5',
      },
      backgroundImage: {
        'button-gradient': 'linear-gradient(to right, theme("colors.gradientL"), theme("colors.gradientR"))',
      },
      keyframes: {
        pulse1: {
          '0%, 100%': { transform: 'scale(1)', backgroundColor: '#bdc0c4' },
          '33.333%': { transform: 'scale(1.5)', backgroundColor: '#525964' },
        },
        pulse2: {
          '0%, 100%': { transform: 'scale(1)', backgroundColor: '#bdc0c4' },
          '33.333%': { transform: 'scale(1.0)', backgroundColor: '#bdc0c4' },
          '66.666%': { transform: 'scale(1.5)', backgroundColor: '#525964' },
        },
        pulse3: {
          '0%, 66.666%': { transform: 'scale(1)', backgroundColor: '##bdc0c4' },
          '100%': { transform: 'scale(1.5)', backgroundColor: '#525964' },
        },
      },
      animation: {
        pulse1: 'pulse1 1.2s infinite',
        pulse2: 'pulse2 1.2s infinite',
        pulse3: 'pulse3 1.2s infinite',
      },
    },
  },
  important: true,
  // darkMode: false
  darkMode: 'class',
};
