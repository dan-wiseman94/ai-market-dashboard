/// <reference types="vitest/config" />
/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from 'node:url';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { playwright } from '@vitest/browser-playwright';
const dirname = typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url));

// More info at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src")
    }
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: ["frontend", "localhost", "127.0.0.1"],
    proxy: {
      "/api": {
        target: "http://web:8000",
        changeOrigin: true
      }
    }
  },
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/__tests__/**", "src/main.tsx", "src/vite-env.d.ts", "src/router.tsx"]
    },
    projects: [{
      extends: true,
      test: {
        globals: true,
        environment: "jsdom",
        setupFiles: ["./src/__tests__/setup.ts"],
        env: {
          VITE_API_BASE_URL: ""
        }
      }
    }, {
      extends: true,
      plugins: [
      // The plugin will run tests for the stories defined in your Storybook config
      // See options at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon#storybooktest
      storybookTest({
        configDir: path.join(dirname, '.storybook')
      })],
      test: {
        name: 'storybook',
        browser: {
          enabled: true,
          headless: true,
          provider: playwright({}),
          instances: [{
            browser: 'chromium'
          }]
        }
      }
    }]
  }
});