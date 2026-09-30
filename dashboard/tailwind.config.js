/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // "white" es la tinta del panel y no el blanco literal: todas las opacidades que el panel usa
      // sobre ella (textos, bordes, superficies) se invierten solas cuando cambia el tema.
      colors: {
        white: 'rgb(var(--tinta) / <alpha-value>)',
        fondo: 'rgb(var(--fondo) / <alpha-value>)',
        superficie: 'rgb(var(--superficie) / <alpha-value>)',
        elevada: 'rgb(var(--elevada) / <alpha-value>)',
        barra: 'rgb(var(--barra) / <alpha-value>)',
      },
    },
  },
  plugins: [],
};
