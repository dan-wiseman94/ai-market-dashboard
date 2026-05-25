export default {
  // Tailwind v4 ships its PostCSS support as a separate package and handles
  // vendor prefixing itself, so autoprefixer is no longer needed.
  plugins: { "@tailwindcss/postcss": {} },
};
